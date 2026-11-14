import argparse
import json
from pathlib import Path
import sys
from .core import run, OrchestrationError

def main():
    parser=argparse.ArgumentParser(description='TETRAVITE static workflow orchestrator (trusted packages only)')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('run')
    p.add_argument('workflow',type=Path)
    p.add_argument('--registry',type=Path,required=True)
    p.add_argument('--input',default='-',help='JSON file or - for stdin')
    p.add_argument('--allow-execution',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    try:
        raw = '{}' if args.dry_run and args.input=='-' else (sys.stdin.read() if args.input=='-' else Path(args.input).read_text(encoding='utf-8'))
        result=run(args.workflow,args.registry,json.loads(raw),allow_execution=args.allow_execution,dry_run=args.dry_run)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OrchestrationError,ValueError,OSError) as e:
        print(json.dumps({'status':'error','code':getattr(e,'code','invalid_request'),'step':getattr(e,'step',None),'message':str(e)}),file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
