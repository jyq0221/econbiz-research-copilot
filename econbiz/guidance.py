"""Plain-language terminal interview; no semantic guesses for unknown fields."""

from .candidates import UNKNOWN


def collect_brief(direction, columns, input_fn=input, output_fn=print):
    output_fn(f'研究方向：{direction}')
    output_fn('先回答你了解的数据事实。不清楚可以留空或选 0；随时按 Ctrl+C 取消，尚未保存的回答不会写入项目。')

    def choice(prompt, maximum):
        while True:
            answer = input_fn(prompt).strip()
            if answer.isdigit() and 0 <= int(answer) <= maximum:
                return int(answer)
            output_fn(f'请输入 0 到 {maximum} 之间的编号。')

    output_fn('你最想回答哪类问题？\n0 尚未确定\n1 描述现象和变化\n2 了解两个指标的关联\n3 判断因果关系\n4 预测未来')
    goal = ['undecided', 'description', 'association', 'causal', 'prediction'][choice('选择编号：', 4)]

    def measure(label):
        output_fn(f'{label}对应哪一列？0 不清楚或当前没有')
        for i, column in enumerate(columns, 1):
            output_fn(f'{i} {column}')
        selected = choice('选择编号：', len(columns))
        if selected == 0:
            return None
        item = {'field': columns[selected - 1]}
        prompts = [('concept', '这一列对应你关心的什么现象？'),
                   ('definition', '这一列具体怎样定义或计算？'),
                   ('unit', '数值的单位是什么？'),
                   ('time', '数据对应哪个期间，或何时可以获知？'),
                   ('source', '数据来自哪里？'),
                   ('missing_meaning', '空白、未披露等标记分别是什么意思？'),
                   ('measurement_limit', '这个指标能代表什么，哪些方面代表不了？')]
        for key, prompt in prompts:
            item[key] = input_fn(prompt + '（不清楚可留空）：').strip() or '待核实'
        confirmed = input_fn('以上说明是否已核实？输入“是”表示已核实，其余回答保留待核实：').strip() == '是'
        item['confirmed'] = confirmed and all(item[key] not in UNKNOWN for key, _ in prompts)
        if not item['confirmed']:
            output_fn('这组字段说明保留为待核实，不会当作已经确认的测量。')
        return item

    focus = measure('最想了解的现象')
    explanatory = measure('你认为可能与它有关的因素') if goal == 'association' else None
    return dict(goal=goal, focus=focus, explanatory=explanatory)
