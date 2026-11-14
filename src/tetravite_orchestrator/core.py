"""Deterministic DAG orchestrator for trusted TETRAVITE packages.

No AI model, dynamic planning, security sandbox or remote package loading.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
from typing import Any
import yaml
from jsonschema import Draft202012Validator
from tetravite_runtime.core import execute, load_package, RuntimeFailure

REF = re.compile(r'^\$\{(input|steps)(?:\.([A-Za-z_][\w-]*))?(?:\.(.*))?\}$')
NAME = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
MAX_STEPS = 32
MAX_WORKFLOW_BYTES = 256_000

class OrchestrationError(Exception):
    def __init__(self, code: str, message: str, step: str | None = None):
        self.code, self.step = code, step
        super().__init__(message)

def _read_config(path: Path) -> dict:
    if path.stat().st_size > MAX_WORKFLOW_BYTES:
        raise OrchestrationError('invalid_workflow', 'Workflow too large')
    try:
        doc = yaml.safe_load(path.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as e:
        raise OrchestrationError('invalid_workflow', str(e)) from e
    if not isinstance(doc, dict) or doc.get('apiVersion') != 'tetravite.dev/workflow/v1alpha1' or doc.get('kind') != 'Workflow':
        raise OrchestrationError('invalid_workflow', 'Unsupported workflow apiVersion/kind')
    return doc

def _walk_refs(value: Any):
    if isinstance(value, str) and value.startswith('${'):
        match = REF.fullmatch(value)
        if not match:
            raise OrchestrationError('invalid_reference', f'Invalid reference: {value}')
        yield match
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)

def _resolve(value: Any, workflow_input: Any, steps: dict) -> Any:
    if isinstance(value, str) and value.startswith('${'):
        match = REF.fullmatch(value)
        if not match:
            raise OrchestrationError('invalid_reference', f'Invalid reference: {value}')
        scope, ident, rest = match.groups()
        if scope == 'input':
            parts = ([ident] if ident else []) + (rest.split('.') if rest else [])
            node = workflow_input
        else:
            if not ident or ident not in steps:
                raise OrchestrationError('missing_reference', f'Unknown step: {ident}')
            node = steps[ident]
            parts = rest.split('.') if rest else []
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            elif isinstance(node, list) and part.isdecimal() and int(part) < len(node):
                node = node[int(part)]
            else:
                raise OrchestrationError('missing_reference', f'Missing reference path: {value}')
        return copy.deepcopy(node)
    if isinstance(value, dict):
        return {k: _resolve(v, workflow_input, steps) for k,v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, workflow_input, steps) for v in value]
    return copy.deepcopy(value)

def validate_workflow(doc: dict) -> list[dict]:
    steps = doc.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise OrchestrationError('invalid_workflow', f'Expected 1..{MAX_STEPS} steps')
    ids = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'id','uses','with'}:
            raise OrchestrationError('invalid_workflow', 'Each step needs exactly id, uses, with')
        sid = step['id']
        if not isinstance(sid, str) or not NAME.fullmatch(sid) or sid in ids:
            raise OrchestrationError('invalid_workflow', f'Invalid or duplicate step id: {sid!r}')
        ids.add(sid)
        if not isinstance(step['uses'], str) or not NAME.fullmatch(step['uses']):
            raise OrchestrationError('invalid_workflow', f'Invalid package alias in {sid}')
        if not isinstance(step['with'], dict):
            raise OrchestrationError('invalid_workflow', f'Input for {sid} must be object')
    for step in steps:
        for match in _walk_refs(step['with']):
            if match.group(1) == 'steps' and (not match.group(2) or match.group(2) not in ids):
                raise OrchestrationError('invalid_reference', f'Unknown dependency in {step["id"]}')
    if 'output' not in doc:
        raise OrchestrationError('invalid_workflow', 'Missing output declaration')
    for match in _walk_refs(doc['output']):
        if match.group(1) == 'steps' and (not match.group(2) or match.group(2) not in ids):
            raise OrchestrationError('invalid_reference', 'Unknown output reference')
    # Stable topological sort, irrespective of declaration order.
    by_id = {s['id']:s for s in steps}
    dependencies = {s['id']:{m.group(2) for m in _walk_refs(s['with']) if m.group(1)=='steps'} for s in steps}
    ordered=[]
    while len(ordered) < len(steps):
        ready = next((s for s in steps if s['id'] not in {x['id'] for x in ordered} and dependencies[s['id']] <= {x['id'] for x in ordered}), None)
        if ready is None:
            raise OrchestrationError('cyclic_workflow', 'Step dependency cycle')
        ordered.append(ready)
    return ordered

def load_registry(path: Path) -> dict[str, Path]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise OrchestrationError('invalid_registry', str(e)) from e
    if not isinstance(data, dict) or not data:
        raise OrchestrationError('invalid_registry', 'Registry must map aliases to local paths')
    registry={}
    for alias, target in data.items():
        if not isinstance(alias,str) or not NAME.fullmatch(alias) or not isinstance(target,str):
            raise OrchestrationError('invalid_registry', 'Invalid alias or path')
        p = Path(target)
        registry[alias] = (path.parent / p).resolve() if not p.is_absolute() else p.resolve()
        if not registry[alias].exists():
            raise OrchestrationError('invalid_registry', f'Missing local package for {alias}')
    return registry

def run(workflow: Path, registry_file: Path, payload: Any, *, allow_execution: bool = False, dry_run: bool = False) -> dict:
    """Run an explicitly trusted, static workflow. No sandboxing or permissions enforcement."""
    doc = _read_config(workflow)
    ordered = validate_workflow(doc)
    registry = load_registry(registry_file)
    for step in ordered:
        if step['uses'] not in registry:
            raise OrchestrationError('unknown_package', f'No registry alias: {step["uses"]}')
    if dry_run:
        return {'status':'dry_run','steps':[{'id':s['id'],'uses':s['uses']} for s in ordered]}
    if not allow_execution:
        raise OrchestrationError('execution_not_authorized', 'Use --allow-execution only with trusted local packages')
    if 'inputSchema' in doc:
        rel = doc['inputSchema']
        if not isinstance(rel,str) or Path(rel).is_absolute() or '\\' in rel or not (workflow.parent/rel).resolve().is_relative_to(workflow.parent.resolve()):
            raise OrchestrationError('invalid_workflow', 'Unsafe workflow inputSchema path')
        schema = json.loads((workflow.parent/rel).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(payload))
        if errors:
            raise OrchestrationError('invalid_input', errors[0].message)
    results={}
    for step in ordered:
        sid=step['id']
        try:
            resolved=_resolve(step['with'], payload, results)
            outcome=execute(registry[step['uses']],resolved,allow_execution=True)
            results[sid]=outcome
        except RuntimeFailure as e:
            raise OrchestrationError('step_failed', f'{e.code}: {e}', sid) from e
        except OrchestrationError as e:
            raise OrchestrationError(e.code,str(e),sid) from e
    output=_resolve(doc['output'],payload,results)
    return {'status':'success','workflow':doc.get('metadata',{}).get('name','unnamed'), 'steps':[{'id':s['id'],'package':s['uses'],'status':'success'} for s in ordered], 'result':output}
