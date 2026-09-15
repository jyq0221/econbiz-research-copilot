"""Small CLI over the same core used by future interfaces."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from .audit import audit_csv
from .candidates import has_prior_results, store_candidates
from .guidance import collect_brief
from .plans import register_plan
from .reports import render_comparison
from .state import Project, WorkflowError, write_json
from .workspace import Workspace


def main(argv=None):
    parser = argparse.ArgumentParser(description='经管实证研究助手：框架与数据盘点')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='初始化研究项目')
    init.add_argument('project', type=Path)
    init.add_argument('--direction', required=True)
    audit = commands.add_parser('audit', help='只读检查 CSV，保留完整报告')
    audit.add_argument('project', type=Path)
    audit.add_argument('csv', type=Path)
    audit.add_argument('--entity', required=True)
    audit.add_argument('--time', required=True)
    audit.add_argument('--numeric', nargs='*', default=[])
    status = commands.add_parser('status', help='查看有效状态、阻塞和下一步')
    status.add_argument('project', type=Path)
    plan = commands.add_parser('plan', help='从 JSON 登记候选方案，等待确认')
    plan.add_argument('project', type=Path)
    plan.add_argument('json', type=Path)
    plan.add_argument('--id', required=True)
    plan.add_argument('--inventory', required=True)
    approve = commands.add_parser('approve', help='记录研究者对具体方案版本的明确确认')
    approve.add_argument('project', type=Path)
    approve.add_argument('id')
    approve.add_argument('--actor', required=True)
    approve.add_argument('--reason', required=True)
    approve.add_argument('--evidence', required=True)
    guide = commands.add_parser('guide', help='用中文问答准备研究路线对照报告')
    guide.add_argument('project', type=Path)
    guide.add_argument('--inventory', required=True)
    guide.add_argument('--brief', type=Path, help='可选：从已有字段说明读取，跳过问答')
    args = parser.parse_args(argv)
    state_path = args.project / 'research_state.json'
    try:
        if args.command == 'init':
            Workspace.create(args.project, args.project.resolve().name, args.direction)
            print(f'项目已建立：{state_path.resolve()}\n下一步：盘点 CSV 字段及数据质量。')
            return 0
        workspace = Workspace.open(args.project)
        project = workspace.project
        if args.command == 'guide':
            inventory = project.require_usable(args.inventory)
            if inventory['kind'] != 'inventory' or 'key' not in inventory['content']:
                raise WorkflowError('请先重新盘点，记录主体与期间字段')
            if args.brief:
                brief = json.loads(args.brief.read_text(encoding='utf-8'))
            else:
                columns = [c for c in inventory['content']['columns'] if c not in inventory['content']['key'].values()]
                brief = collect_brief(project.snapshot()['direction'], columns)
                if has_prior_results(project):
                    brief['exploration_reason'] = input('项目已有结果。现在提出这组问题的原因是什么？（会标记为结果后探索）：').strip()
            prefix = 'guidance-' + uuid4().hex[:12]
            updated, comparison = store_candidates(project, args.inventory, brief, prefix)
            report_path = workspace.path('research_reports') / f'{prefix}.html'
            rendered = render_comparison(comparison)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered, encoding='utf-8')
            workspace.project = updated
            workspace.save()
            print(f'已准备 {len(comparison["plans"])} 条讨论路线，尚未代你确认任何方案。')
            print(f'用浏览器打开报告：{report_path.resolve()}')
            print('下一步：' + comparison['recommendation'])
            for question in comparison['questions']:
                print('待核实：' + question)
            return 0
        if args.command == 'plan':
            content = json.loads(args.json.read_text(encoding='utf-8'))
            register_plan(project, args.id, content, args.inventory)
            workspace.save()
            print(f'候选方案 {args.id} 已登记，待核对研究目标、字段含义、样本及方法条件。')
            return 0
        if args.command == 'approve':
            project.approve(args.id, args.actor, args.reason, args.evidence)
            workspace.save()
            print(f'{args.id} 当前版本的确认已记录；这不代表模型已估计或识别假设已验证。')
            return 0
        if args.command == 'audit':
            artifact_id = 'inventory-' + uuid4().hex[:12]
            source_id = 'source-' + uuid4().hex[:12]
            workspace.import_file(source_id, args.csv, role='raw_data', reason='用户请求盘点该 CSV')
            artifact = workspace.audit(artifact_id, source_id, entity=args.entity, time=args.time, numeric=args.numeric)
            report = artifact['content']
            report_path = workspace.root / artifact['files'][0]['path']
            print(f'{artifact_id}：{report["rows"]} 行，{report["entities"]} 个主体，检查 {report["check_status"]}')
            print(f'报告：{report_path.resolve()}')
            print('下一步：处理报告中的错误，并核实字段含义、单位、时间和缺失规则。')
            return 0 if report['check_status'] == 'passed' else 2
        state = project.snapshot()
        print(f'研究方向：{state["direction"]}')
        for key, a in state['artifacts'].items():
            print(f'{key} v{a["version"]} | 执行：{a["execution_status"]} | 检查：{a["check_status"]}')
            try:
                project.require_usable(key)
            except WorkflowError as exc:
                print(f'  当前不可消费：{exc}')
        print('下一步：先解决失败、过期或需要决策的产物，再继续依赖它们的分析。')
        print('当前框架尚未接入统计估计与自动结果解释。')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('已取消问答，尚未保存的回答未写入项目。', file=sys.stderr)
        return 2
    except (WorkflowError, OSError, ValueError) as exc:
        print(f'无法继续：{exc}', file=sys.stderr)
        return 2
