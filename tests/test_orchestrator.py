import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from tetravite_orchestrator.core import run, validate_workflow, OrchestrationError, _resolve

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples'

class TestOrchestrator(unittest.TestCase):
    def test_dag_orders_dependencies(self):
        doc=yaml.safe_load((EXAMPLE/'workflow.yaml').read_text())
        doc['steps'].reverse()
        self.assertEqual([s['id'] for s in validate_workflow(doc)], ['first','second'])

    def test_cycle_rejected(self):
        doc=yaml.safe_load((EXAMPLE/'workflow.yaml').read_text())
        doc['steps'][0]['with']['name']='${steps.second.result.greeting}'
        with self.assertRaises(OrchestrationError) as ctx:
            validate_workflow(doc)
        self.assertEqual(ctx.exception.code,'cyclic_workflow')

    def test_unknown_reference_rejected(self):
        doc=yaml.safe_load((EXAMPLE/'workflow.yaml').read_text())
        doc['steps'][0]['with']['name']='${steps.missing.result}'
        with self.assertRaises(OrchestrationError):
            validate_workflow(doc)

    def test_reference_preserves_types(self):
        self.assertEqual(_resolve({'items':'${input.items}'},{'items':[1,2]},{}),{'items':[1,2]})

    def test_missing_path_fails(self):
        with self.assertRaises(OrchestrationError):
            _resolve('${input.nope}',{}, {})

    def test_dry_run(self):
        result=run(EXAMPLE/'workflow.yaml',EXAMPLE/'registry.example.json',{},dry_run=True)
        self.assertEqual([s['id'] for s in result['steps']],['first','second'])

    def test_execution_requires_consent(self):
        with self.assertRaises(OrchestrationError) as ctx:
            run(EXAMPLE/'workflow.yaml',EXAMPLE/'registry.example.json',{'name':'Ada'})
        self.assertEqual(ctx.exception.code,'execution_not_authorized')

    def test_two_step_integration(self):
        result=run(EXAMPLE/'workflow.yaml',EXAMPLE/'registry.example.json',{'name':'Ada'},allow_execution=True)
        self.assertEqual(result['result'],{'firstGreeting':'Hello, Ada','chainedGreeting':'Hello, Hello, Ada'})

    def test_invalid_input(self):
        with self.assertRaises(OrchestrationError) as ctx:
            run(EXAMPLE/'workflow.yaml',EXAMPLE/'registry.example.json',{'name':3},allow_execution=True)
        self.assertEqual(ctx.exception.code,'invalid_input')

    def test_step_error(self):
        doc=yaml.safe_load((EXAMPLE/'workflow.yaml').read_text())
        doc['steps'][1]['with']['name']='${steps.first.result.nonexistent}'
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'workflow.yaml';f.write_text(yaml.safe_dump(doc))
            # schema path must be valid from temp dir
            doc.pop('inputSchema');f.write_text(yaml.safe_dump(doc))
            with self.assertRaises(OrchestrationError) as ctx:
                run(f,EXAMPLE/'registry.example.json',{'name':'Ada'},allow_execution=True)
            self.assertEqual(ctx.exception.code,'missing_reference')
            self.assertEqual(ctx.exception.step,'second')

if __name__ == '__main__':
    unittest.main()
