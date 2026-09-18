"""A small, explicit TeX text/math vocabulary; no file or macro commands."""

import re
from .state import WorkflowError, require_text

ESCAPES = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '&': r'\&',
           '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_', '^': r'\textasciicircum{}',
           '~': r'\textasciitilde{}', '\n': r'\EBBreak{}', '\t': r'\EBTab{}', '\r': r'\EBReturn{}'}
DECODE = {v: k for k, v in ESCAPES.items()}
MATH_COMMANDS = set(('alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa '
                     'lambda mu nu xi pi rho varrho sigma tau upsilon phi varphi chi psi omega '
                     'Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega '
                     'frac sqrt sum prod int log ln exp min max lim sin cos tan '
                     'hat bar tilde vec mathbf mathrm mathit mathcal '
                     'left right cdot times div pm mp le leq ge geq ne neq approx equiv '
                     'in notin subset subseteq cup cap infty partial nabla '
                     'to propto ell ldots cdots underbrace overbrace').split())


def escape_text(value):
    if not isinstance(value, str) or any(ord(c) < 32 and c not in '\n\t\r' for c in value):
        raise WorkflowError('LaTeX 文本须为不含控制字符的字符串')
    return ''.join(ESCAPES.get(c, c) for c in value)


def decode_text(value):
    """Decode only our text language, rejecting unrecognized TeX instructions."""
    parts, i = [], 0
    while i < len(value):
        if value[i] == '\\':
            token = next((t for t in DECODE if value.startswith(t, i)), None)
            if token is None:
                raise WorkflowError('源文件包含未知文字命令')
            parts.append(DECODE[token]); i += len(token)
        else:
            if value[i] in '{}&%$#_^~':
                raise WorkflowError('源文件文字包含未转义字符')
            parts.append(value[i]); i += 1
    return ''.join(parts)


def validate_math(value):
    require_text(value, '公式')
    if len(value) > 4096 or '^^' in value:
        raise WorkflowError('公式超出支持范围')
    depth, i, left = 0, 0, 0
    while i < len(value):
        c = value[i]
        if c == '\\':
            m = re.match(r'\\([A-Za-z]+|[,;! {}|])', value[i:])
            if not m or (m[1].isalpha() and m[1] not in MATH_COMMANDS):
                raise WorkflowError('公式包含未支持的命令')
            if m[1] == 'left': left += 1
            if m[1] == 'right':
                left -= 1
                if left < 0: raise WorkflowError('公式定界符不配对')
            i += len(m[0]); continue
        if c == '{':
            depth += 1
            if depth > 32: raise WorkflowError('公式嵌套过深')
        elif c == '}':
            depth -= 1
            if depth < 0: raise WorkflowError('公式分组不配对')
        elif not (c.isascii() and (c.isalnum() or c in ' _^+-=*/().,[]|<>:;!\n')):
            raise WorkflowError('公式包含未支持的字符；希腊字母请使用数学命令')
        i += 1
    if depth or left:
        raise WorkflowError('公式分组或定界符不配对')
    return value


def group_at(text, start):
    """Read one braced argument, accounting for escaped braces and text macros."""
    if start >= len(text) or text[start] != '{':
        raise WorkflowError('源文件缺少命令参数')
    depth, i = 1, start + 1
    while i < len(text):
        if text[i] == '\\':
            i += 2; continue
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0: return text[start+1:i], i+1
        i += 1
    raise WorkflowError('源文件参数不完整')


def arguments(text, command):
    values, pos = [], 0
    token = '\\'+command+'{'
    while True:
        start = text.find(token, pos)
        if start < 0: return values
        value, pos = group_at(text, start+len(token)-1)
        values.append(value)
