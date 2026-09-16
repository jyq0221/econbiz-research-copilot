"""Render explicit recipes as portable Python or native, dependency-free Mata.

Python execution uses the package copied into its run bundle. The Stata path
parses CSV as strings in Mata, preserving source cells without type inference.
Both produce an execution audit, never a claim of independent verification.
"""

import json
import re

from .preprocessing import validate_recipe
from .state import WorkflowError


def _literal(value):
    # Macro markers, quotes and controls are emitted as character expressions,
    # so user labels can never become Stata macros or executable source.
    parts, chunk = [], ''
    for char in value:
        if char in '"`$' or ord(char) < 32:
            if chunk:
                parts.append('"' + chunk + '"')
                chunk = ''
            parts.append(f'char({ord(char)})')
        else:
            chunk += char
    if chunk:
        parts.append('"' + chunk + '"')
    return '(' + '+'.join(parts or ['""']) + ')'


def _vector(values):
    return '(' + ','.join(_literal(value) for value in values) + ')' if values else 'J(1,0,"")'


def render_preparation_script(recipe, *, backend, input_name='input.csv', output_name='processed.csv'):
    """Return reviewed source; execution and file registration belong to runner.

    Native floating output roundtrips numerically but may differ in its last
    printed digit from Python. Native text comparisons and categorical grouping
    therefore accept original fields or derived indicators, not derived floats.
    """
    recipe = validate_recipe(recipe)
    if backend not in ('python', 'stata'):
        raise WorkflowError('预处理脚本 backend 须为 python 或 stata')
    for name in (input_name, output_name):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*\.csv', name):
            raise WorkflowError('预处理文件名须为安全的 CSV 基础文件名')
    if input_name == output_name:
        raise WorkflowError('预处理输出不可覆盖输入')
    encoded = json.dumps(recipe, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    if backend == 'python':
        return ('from pathlib import Path\nimport json\nfrom econbiz.preprocessing import prepare_data\n'
                'root = Path(__file__).resolve().parent\n'
                f'recipe = json.loads({encoded!r})\n'
                f'output, audit = prepare_data((root / {input_name!r}).read_bytes(), recipe)\n'
                f'(root / {output_name!r}).write_bytes(output)\n'
                '(root / "preparation-audit.json").write_text(json.dumps(audit, ensure_ascii=False, '
                'allow_nan=False, indent=2) + "\\n", encoding="utf-8")\n')
    names = list(recipe['keys'])
    numeric_derived = set()
    for step in recipe['steps']:
        categorical = list(step.get('by', [])) + list(step.get('entity', []))
        if step['op'] == 'indicator' or (step['op'] == 'filter' and step['operator'] in {'eq', 'ne', 'in', 'not_in'}):
            categorical.append(step['source'])
        if numeric_derived.intersection(categorical):
            raise WorkflowError('Stata 不支持把数值派生列用于文本比较、类别标记或分组；请用数值筛选或原始类别列')
        if 'target' in step and step['op'] != 'indicator':
            numeric_derived.add(step['target'])
        if (step['op'] == 'filter' and type(step.get('value')) in {int, float}
                and abs(step['value']) >= 8.988465674311579e307):
            raise WorkflowError('Stata 数值筛选阈值超出原生有限 double 范围')
        if step['op'] == 'filter' and type(step.get('value')) is int and abs(step['value']) >= 2 ** 53:
            raise WorkflowError('Stata 整数筛选阈值超出精确 double 整数范围')
        names.extend(step[k] for k in ('source', 'target', 'numerator', 'denominator', 'time') if k in step)
        for key in ('sources', 'by', 'entity'):
            names.extend(step.get(key, []))
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}', name) for name in names):
        raise WorkflowError('首版 Stata 预处理引用的字段仅支持字母开头的 ASCII 名称，最长 32 字符')
    lines = ['version 19.0', 'clear all', 'set more off', 'set varabbrev off', _MATA,
             'mata:', f'eb_t = eb_read({_literal(input_name)})',
             f'eb_keys(eb_t, {_vector(recipe["keys"])})', 'eb_before = rows(eb_t.data)',
             'eb_reports = "["']
    for index, step in enumerate(recipe['steps'], 1):
        op = step['op']
        params = json.dumps(step, ensure_ascii=False, separators=(',', ':'))
        args = [f'{index}', _literal(op), _literal(params)]
        if op == 'filter':
            value = step.get('value')
            values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
            number = repr(value) if type(value) in {int, float} else '.'
            call = f'eb_filter(eb_t,{_literal(step["source"])},{_literal(step["operator"])},{_vector(values)},{number})'
        elif op in {'winsor', 'center', 'standardize'}:
            call = (f'eb_group(eb_t,{_literal(op)},{_literal(step["source"])},{_literal(step["target"])},'
                    f'{_vector(step["by"])},{step.get("lower", 0)},{step.get("upper", 1)},'
                    f'{step.get("ddof", 0)},{_literal(step.get("zero", "error"))})')
        elif op in {'lag', 'difference'}:
            call = (f'eb_panel(eb_t,{_literal(op)},{_literal(step["source"])},{_literal(step["target"])},'
                    f'{_vector(step["entity"])},{_literal(step["time"])},{step["interval"]})')
        else:
            sources = (step['sources'] if op == 'interaction' else [step['numerator'], step['denominator']]
                       if op == 'ratio' else [step['source']])
            call = (f'eb_simple(eb_t,{_literal(op)},{_vector(sources)},{_literal(step["target"])},'
                    f'{_literal(step.get("invalid", step.get("zero", step.get("missing", ""))))},'
                    f'{_literal(step.get("value", ""))})')
        if index > 1:
            lines.append('eb_reports = eb_reports + ","')
        lines.extend(['eb_n = rows(eb_t.data)', f'eb_detail = {call}',
                      'eb_reports = eb_reports + eb_report(' + ','.join(args) + ',eb_n,rows(eb_t.data),eb_detail)'])
    lines.extend(['eb_reports = eb_reports + "]"', f'eb_write(eb_t,{_literal(output_name)})',
                  'eb_recipe = ""'])
    # Keep generated lines bounded even for recipes containing many operations.
    for offset in range(0, len(encoded), 100):
        lines.append('eb_recipe = eb_recipe + ' + _literal(encoded[offset:offset + 100]))
    lines.extend(['eb_audit(eb_before,rows(eb_t.data),eb_recipe,eb_reports)', 'end', ''])
    return '\n'.join(lines)


_MATA = r'''
mata:
struct eb_table {
    string rowvector names
    string matrix data
}
void eb_fail(string scalar message) {
    errprintf("Preparation failed: %s\n", message)
    _error(3498)
}
string scalar eb_cell(real scalar x) {
    real scalar epos, exponent, point, i
    string scalar encoded, digits, sign, result, suffix
    if (missing(x)) return("")
    if (x==0) return("0")
    encoded=strtrim(strofreal(abs(x),"%25.16e"))
    epos=strpos(encoded,"e")
    if (!epos) eb_fail("Native scientific serialization failed")
    exponent=strtoreal(substr(encoded,epos+1,.))
    digits=subinstr(substr(encoded,1,epos-1),".","")
    while (strlen(digits)>1 & substr(digits,strlen(digits),1)=="0") digits=substr(digits,1,strlen(digits)-1)
    sign=x<0 ? "-" : ""
    if (exponent < -4 | exponent >= 17) {
        result=substr(digits,1,1)
        if (strlen(digits)>1) result=result+"."+substr(digits,2,.)
        suffix=strtrim(strofreal(abs(exponent),"%4.0f"))
        if (strlen(suffix)<2) suffix="0"+suffix
        result=result+"e"+(exponent<0 ? "-" : "+")+suffix
    }
    else {
        point=exponent+1
        if (point<=0) {
            result="0."
            for (i=1;i<=-point;i++) result=result+"0"
            result=result+digits
        }
        else if (point>=strlen(digits)) {
            result=digits
            for (i=strlen(digits)+1;i<=point;i++) result=result+"0"
        }
        else result=substr(digits,1,point)+"."+substr(digits,point+1,.)
    }
    result=sign+result
    if (strtoreal(result)!=x) eb_fail("Native numeric serialization did not roundtrip")
    return(result)
}
string scalar eb_num(real scalar x) {
    if (missing(x)) return("null")
    return(eb_cell(x))
}
string scalar eb_json(string scalar s) {
    real scalar i, a
    string scalar out, c
    out = char(34)
    for (i=1; i<=strlen(s); i++) {
        c = substr(s,i,1)
        a = ascii(c)
        if (c==char(34) | c==char(92)) out = out + char(92) + c
        else if (a==10) out = out + char(92) + "n"
        else if (a==13) out = out + char(92) + "r"
        else if (a==9) out = out + char(92) + "t"
        else if (a<32) eb_fail("Unsupported control character in audit label")
        else out = out + c
    }
    return(out + char(34))
}
real scalar eb_col(struct eb_table scalar t, string scalar name) {
    real rowvector found
    found = selectindex(t.names:==name)
    if (cols(found)!=1) eb_fail("Missing or duplicate column: " + name)
    return(found[1])
}
real rowvector eb_cols(struct eb_table scalar t, string rowvector names) {
    real scalar i
    real rowvector result
    result = J(1,cols(names),.)
    for (i=1; i<=cols(names); i++) result[i] = eb_col(t,names[i])
    return(result)
}
void eb_appendrow(struct eb_table scalar t, string rowvector row) {
    if (cols(t.names)==0) {
        t.names = row
        t.data = J(0,cols(row),"")
    }
    else {
        if (cols(row)!=cols(t.names)) eb_fail("CSV row width differs from header")
        t.data = t.data \ row
    }
}
struct eb_table scalar eb_read(string scalar filename) {
    struct eb_table scalar t
    real scalar f, i, quoted, closed, started, n
    string scalar raw, c, field
    string matrix chunk
    string rowvector row
    f = fopen(filename,"r")
    raw = ""
    while (rows(chunk=fread(f,65536))) raw = raw + chunk
    fclose(f)
    if (ustrinvalidcnt(raw)) eb_fail("CSV contains invalid UTF-8 bytes")
    if (substr(raw,1,3)==char(239)+char(187)+char(191)) raw = substr(raw,4,.)
    if (strpos(raw,char(0))) eb_fail("NUL bytes are unsupported")
    t.names = J(1,0,"")
    t.data = J(0,0,"")
    row = J(1,0,"")
    field = ""
    quoted = closed = started = 0
    n = strlen(raw)
    for (i=1; i<=n; i++) {
        c = substr(raw,i,1)
        if (quoted) {
            if (c==char(34)) {
                if (i<n & substr(raw,i+1,1)==char(34)) {
                    field = field + c
                    i++
                }
                else {
                    quoted=0
                    closed=1
                }
            }
            else field = field + c
        }
        else if (c=="," | c==char(10) | c==char(13)) {
            row = row,field
            field = ""
            closed = started = 0
            if (c!=",") {
                eb_appendrow(t,row)
                row = J(1,0,"")
                if (c==char(13) & substr(raw,i+1,1)==char(10)) i++
            }
        }
        else {
            if (closed) eb_fail("Unexpected text after CSV quote")
            if (c==char(34) & !started) quoted=1
            else field = field + c
            started=1
        }
    }
    if (quoted) eb_fail("Unclosed CSV quote")
    if (cols(row) | started | closed) eb_appendrow(t,(row,field))
    if (!cols(t.names) | !rows(t.data)) eb_fail("CSV header or observations missing")
    for (i=1; i<=cols(t.names); i++) {
        if (strtrim(t.names[i])=="" | sum(t.names:==t.names[i])!=1) eb_fail("Empty/duplicate CSV header")
    }
    return(t)
}
void eb_keys(struct eb_table scalar t, string rowvector names) {
    real rowvector indices
    real scalar i, j
    indices = eb_cols(t,names)
    for (i=1; i<=rows(t.data); i++) {
        if (any(t.data[i,indices]:=="")) eb_fail("Missing identity key")
        for (j=1; j<i; j++) if (all(t.data[i,indices]:==t.data[j,indices])) eb_fail("Duplicate identity key")
    }
}
real scalar eb_number(string scalar s) {
    real scalar value
    if (s=="") return(.)
    if (!regexm(s,"^ *[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)? *$")) eb_fail("Unexplained numeric text: " + s)
    value = strtoreal(s)
    if (missing(value)) eb_fail("Unexplained or nonfinite numeric text: " + s)
    return(value)
}
real colvector eb_numbers(struct eb_table scalar t, real scalar column) {
    real scalar i
    real colvector values
    values = J(rows(t.data),1,.)
    for (i=1; i<=rows(t.data); i++) values[i] = eb_number(t.data[i,column])
    return(values)
}
void eb_target(struct eb_table scalar t, string scalar name, real colvector output) {
    real scalar i
    string colvector values
    if (any(t.names:==name)) eb_fail("Target would overwrite source column: " + name)
    values = J(rows(output),1,"")
    for (i=1; i<=rows(output); i++) values[i] = eb_cell(output[i])
    t.names = t.names,name
    t.data = t.data,values
}
string scalar eb_counts(real colvector output, real scalar affected, real scalar invalid) {
    real scalar count
    count = sum(output:<.)
    return(char(34)+"affected"+char(34)+":"+eb_num(affected)+","+
           char(34)+"invalid_to_missing"+char(34)+":"+eb_num(invalid)+","+
           char(34)+"output_nonmissing"+char(34)+":"+eb_num(count)+","+
           char(34)+"output_missing"+char(34)+":"+eb_num(rows(output)-count))
}
string scalar eb_simple(struct eb_table scalar t, string scalar op, string rowvector sources,
                       string scalar target, string scalar policy, string scalar category) {
    real rowvector columns, values
    real colvector output
    real scalar i, j, invalid, value
    columns = eb_cols(t,sources)
    output = J(rows(t.data),1,.)
    invalid = 0
    for (i=1; i<=rows(t.data); i++) {
        if (op=="indicator") {
            if (t.data[i,columns[1]]=="" & policy=="error") eb_fail("Missing indicator source")
            if (t.data[i,columns[1]]!="" | policy=="zero") output[i] = t.data[i,columns[1]]==category
        }
        else {
            values = J(1,cols(columns),.)
            for (j=1; j<=cols(columns); j++) values[j] = eb_number(t.data[i,columns[j]])
            if (any(values:>=.)) continue
            if (op=="ln" | op=="log1p") {
                if (values[1]<=-(op=="log1p")) {
                    if (policy=="error") eb_fail("Logarithm domain error")
                    invalid++
                    continue
                }
                output[i] = op=="ln" ? ln(values[1]) : ln1p(values[1])
            }
            else if (op=="ratio") {
                if (values[2]==0) {
                    if (policy=="error") eb_fail("Zero ratio denominator")
                    invalid++
                    continue
                }
                output[i] = values[1]/values[2]
            }
            else {
                value = 1
                for (j=1; j<=cols(values); j++) value = value*values[j]
                output[i] = value
            }
            if (missing(output[i])) eb_fail("Nonfinite arithmetic result")
        }
    }
    eb_target(t,target,output)
    return(eb_counts(output,sum(output:<.)+invalid,invalid))
}
real scalar eb_quantile(real colvector v, real scalar p) {
    real scalar a, fraction
    if (!rows(v)) return(.)
    a = (rows(v)-1)*p+1
    fraction = a-floor(a)
    return(v[floor(a)]*(1-fraction)+v[ceil(a)]*fraction)
}
string scalar eb_group(struct eb_table scalar t, string scalar op, string scalar source,
                      string scalar target, string rowvector by, real scalar lower,
                      real scalar upper, real scalar ddof, string scalar policy) {
    real rowvector columns
    real colvector values, output, done, indices, v, centered
    real scalar i, j, n, lo, hi, m, sd, scale, invalid, affected, changed
    string scalar reports, detail, group
    values = eb_numbers(t,eb_col(t,source))
    columns = eb_cols(t,by)
    output = J(rows(values),1,.)
    done = J(rows(values),1,0)
    reports = "["
    invalid = affected = 0
    for (i=1; i<=rows(values); i++) {
        if (done[i]) continue
        indices = J(0,1,.)
        for (j=i; j<=rows(values); j++) {
            if (!cols(columns) | all(t.data[i,columns]:==t.data[j,columns])) indices=indices\j
        }
        done[indices] = J(rows(indices),1,1)
        v = select(values[indices],values[indices]:<.)
        v = sort(v,1)
        n = rows(v)
        group = "{"
        for (j=1; j<=cols(by); j++) {
            if (j>1) group=group+","
            group=group+eb_json(by[j])+":"+eb_json(t.data[i,columns[j]])
        }
        group=group+"}"
        detail = char(34)+"group"+char(34)+":"+group+","+char(34)+"n_rows"+char(34)+":"+eb_num(rows(indices))+","+
                 char(34)+"n_nonmissing"+char(34)+":"+eb_num(n)
        if (op=="winsor") {
            lo = eb_quantile(v,lower)
            hi = eb_quantile(v,upper)
            for (j=1; j<=rows(indices); j++) {
                if (!missing(values[indices[j]])) output[indices[j]]=min((max((values[indices[j]],lo)),hi))
            }
            detail = detail+","+char(34)+"lower_threshold"+char(34)+":"+eb_num(lo)+","+
                     char(34)+"upper_threshold"+char(34)+":"+eb_num(hi)+","+
                     char(34)+"quantile_method"+char(34)+":"+eb_json("linear_n_minus_1")
        }
        else {
            m = sd = .
            if (n) {
                if (v[1]==v[n]) m=v[1]
                else if (any((v:-v[1]):>=.)) m=quadsum(v:/n)
                else m=v[1]+quadsum((v:-v[1]):/n)
            }
            if (op=="standardize" & n>ddof) {
                centered=v:-m
                if (any(centered:>=.)) eb_fail("Nonfinite centering during variance calculation")
                scale=max(abs(centered))
                sd=scale==0 ? 0 : scale*sqrt(quadsum((centered:/scale):^2)/(n-ddof))
                if (scale>0 & sd==0) eb_fail("Standard deviation underflow")
            }
            if (n & missing(m)) eb_fail("Nonfinite group mean")
            if (op=="standardize" & n>ddof & missing(sd)) eb_fail("Nonfinite group variance")
            if (op=="standardize" & n & (missing(sd) | sd==0) & policy=="error") eb_fail("Undefined/zero standard deviation")
            for (j=1; j<=rows(indices); j++) {
                if (missing(values[indices[j]])) continue
                if (op=="center") output[indices[j]]=values[indices[j]]-m
                else if (missing(sd) | sd==0) {
                    invalid++
                    continue
                }
                else output[indices[j]]=(values[indices[j]]-m)/sd
                if (missing(output[indices[j]])) eb_fail("Nonfinite centered/standardized result")
            }
            detail = detail+","+char(34)+"mean"+char(34)+":"+eb_num(m)
            if (op=="standardize") detail=detail+","+char(34)+"sd"+char(34)+":"+eb_num(sd)+","+char(34)+"ddof"+char(34)+":"+eb_num(ddof)
        }
        changed = sum(output[indices]:!=values[indices])
        affected = affected+changed
        if (reports!="[") reports=reports+","
        reports = reports+"{"+detail+","+char(34)+"affected"+char(34)+":"+eb_num(changed)+"}"
    }
    reports=reports+"]"
    eb_target(t,target,output)
    return(eb_counts(output,affected,invalid)+","+char(34)+"groups"+char(34)+":"+reports)
}
string scalar eb_panel(struct eb_table scalar t, string scalar op, string scalar source,
                      string scalar target, string rowvector entity, string scalar time, real scalar interval) {
    real rowvector columns
    real colvector periods, values, output
    real scalar i, j, found, unmatched
    columns = eb_cols(t,entity)
    periods = eb_numbers(t,eb_col(t,time))
    values = eb_numbers(t,eb_col(t,source))
    output = J(rows(values),1,.)
    unmatched=0
    for (i=1; i<=rows(values); i++) {
        if (missing(periods[i]) | abs(periods[i])>=2^53 | any(t.data[i,columns]:=="")) eb_fail("Invalid entity/integer time")
        if (!regexm(t.data[i,eb_col(t,time)],"^ *[+-]?[0-9]+([.]0+)? *$")) eb_fail("Time must be a decimal integer")
        for (j=1; j<i; j++) {
            if (periods[i]==periods[j] & all(t.data[i,columns]:==t.data[j,columns])) eb_fail("Duplicate panel entity/time")
        }
    }
    for (i=1; i<=rows(values); i++) {
        found=0
        for (j=1; j<=rows(values); j++) {
            if (periods[j]==periods[i]-interval & all(t.data[i,columns]:==t.data[j,columns])) {
                found=j
                break
            }
        }
        if (!found) {
            unmatched++
            continue
        }
        if (op=="lag") output[i]=values[found]
        else if (!missing(values[i]) & !missing(values[found])) {
            output[i]=values[i]-values[found]
            if (missing(output[i])) eb_fail("Nonfinite difference")
        }
    }
    eb_target(t,target,output)
    return(eb_counts(output,sum(output:<.),0)+","+char(34)+"unmatched_periods"+char(34)+":"+eb_num(unmatched))
}
string scalar eb_filter(struct eb_table scalar t, string scalar source, string scalar op,
                       string rowvector wanted, real scalar threshold) {
    real scalar col, i, number, before
    real colvector keep
    string scalar value
    col = eb_col(t,source)
    before = rows(t.data)
    keep = J(before,1,0)
    for (i=1; i<=before; i++) {
        value = t.data[i,col]
        if (op=="is_missing") keep[i]=value==""
        else if (op=="not_missing") keep[i]=value!=""
        else if (op=="eq") keep[i]=value==wanted[1]
        else if (op=="ne") keep[i]=value!=wanted[1]
        else if (op=="in") keep[i]=any(wanted:==value)
        else if (op=="not_in") keep[i]=!any(wanted:==value)
        else {
            number=eb_number(value)
            if (missing(number)) continue
            if (op=="gt") keep[i]=number>threshold
            if (op=="ge") keep[i]=number>=threshold
            if (op=="lt") keep[i]=number<threshold
            if (op=="le") keep[i]=number<=threshold
        }
    }
    t.data=select(t.data,keep)
    return(char(34)+"affected"+char(34)+":"+eb_num(before-rows(t.data))+","+char(34)+"invalid_to_missing"+char(34)+":0")
}
string scalar eb_report(real scalar index, string scalar op, string scalar parameters,
                       real scalar before, real scalar after, string scalar detail) {
    return("{"+char(34)+"index"+char(34)+":"+eb_num(index)+","+char(34)+"op"+char(34)+":"+eb_json(op)+","+
           char(34)+"parameters"+char(34)+":"+parameters+","+char(34)+"n_before"+char(34)+":"+eb_num(before)+","+
           char(34)+"n_after"+char(34)+":"+eb_num(after)+","+detail+"}")
}
void eb_write(struct eb_table scalar t, string scalar filename) {
    real scalar f, i, j
    string scalar line, cell
    f = fopen(filename,"w")
    for (i=0; i<=rows(t.data); i++) {
        line=""
        for (j=1; j<=cols(t.names); j++) {
            if (j>1) line=line+","
            cell = i==0 ? t.names[j] : t.data[i,j]
            cell = subinstr(cell,char(34),char(34)+char(34))
            line=line+char(34)+cell+char(34)
        }
        fput(f,line)
    }
    fclose(f)
}
void eb_audit(real scalar before, real scalar after, string scalar recipe, string scalar reports) {
    real scalar f
    string scalar result
    result="{"+char(34)+"schema_version"+char(34)+":1,"+char(34)+"operation"+char(34)+":"+eb_json("prepare_data")+","+
           char(34)+"backend"+char(34)+":"+eb_json("stata")+","+char(34)+"recipe"+char(34)+":"+recipe+","+
           char(34)+"n_before"+char(34)+":"+eb_num(before)+","+char(34)+"n_after"+char(34)+":"+eb_num(after)+","+
           char(34)+"missing_rule"+char(34)+":"+eb_json("empty_string_only")+","+
           char(34)+"verification"+char(34)+":"+eb_json("not_independently_verified")+","+
           char(34)+"steps"+char(34)+":"+reports+"}"
    f=fopen("preparation-audit.json","w")
    fput(f,result)
    fclose(f)
}
end
'''
