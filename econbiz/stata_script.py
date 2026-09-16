"""Generate fixed, alias-only Stata programs and native Mata export helpers."""


MATA_HELPERS = r'''
mata:
void eb_matrix(string scalar filename, real matrix a) {
    real scalar f, i, j
    string scalar line
    f = fopen(filename, "w")
    for (i=1; i<=rows(a); i++) {
        line = ""
        for (j=1; j<=cols(a); j++) {
            if (j>1) line = line + ","
            line = line + strtrim(strofreal(a[i,j], "%24.17g"))
        }
        fput(f, line)
    }
    fclose(f)
}
real scalar eb_q(real colvector x, real scalar p) {
    real scalar a, lo, hi
    a = (rows(x)-1)*p+1
    lo = floor(a)
    hi = ceil(a)
    return((1-(a-lo))*x[lo]+(a-lo)*x[hi])
}
void eb_describe(string scalar names) {
    real matrix x, output
    real colvector v
    real scalar j, n, m, sd
    x = st_data(., tokens(names))
    n = rows(x)
    output = J(cols(x), 9, .)
    for (j=1; j<=cols(x); j++) {
        v = sort(x[,j], 1)
        m = mean(v)
        sd = .
        if (n>1) sd = sqrt(quadcross(v:-m,v:-m)/(n-1))
        output[j,] = (n,m,sd,v[1],eb_q(v,.25),eb_q(v,.5),eb_q(v,.75),v[n],j)
    }
    eb_matrix("descriptive.csv", output)
}
void eb_stripes() {
    string matrix names
    real scalar f, i
    names = st_matrixcolstripe("eb_b")
    f = fopen("stripes.csv", "w")
    fput(f, "position,name")
    for (i=1; i<=rows(names); i++) fput(f, strofreal(i)+","+names[i,2])
    fclose(f)
}
string scalar eb_num(string scalar name) {
    return(strtrim(strofreal(st_numscalar(name), "%24.17e")))
}
void eb_metadata(real scalar linear, string scalar run_token) {
    real scalar f
    f = fopen("metadata.json", "w")
    fput(f, "{")
    fput(f, `""run_token": ""'+run_token+`"","')
    fput(f, `""nobs": "'+strtrim(strofreal(st_nobs()))+",")
    if (linear) {
        fput(f, `""cmd": ""'+st_global("e(cmd)")+`"","')
        fput(f, `""cmdline": ""'+st_global("e(cmdline)")+`"","')
        fput(f, `""depvar": ""'+st_global("e(depvar)")+`"","')
        fput(f, `""absvar": ""'+st_global("e(absvar)")+`"","')
        fput(f, `""vce": ""'+st_global("e(vce)")+`"","')
        fput(f, `""clustvar": ""'+st_global("e(clustvar)")+`"","')
        fput(f, `""estimation_nobs": "'+eb_num("e(N)")+",")
        fput(f, `""inference_df": "'+eb_num("e(df_r)")+",")
        fput(f, `""absorbed_df": "'+eb_num("e(df_a)")+",")
        fput(f, `""absorbed_categories": "'+eb_num("e(k_absorb)")+",")
        fput(f, `""rss": "'+eb_num("e(rss)")+",")
        if (st_global("e(vce)")=="cluster") fput(f, `""cluster_count": "'+eb_num("e(N_clust)")+",")
        else fput(f, `""cluster_count": null,"')
    }
    else fput(f, `""cmd": "mata: eb_describe","')
    fput(f, `""complete": true}"')
    fclose(f)
}
end
'''


def regression_command(mapping):
    """Only safe generated identifiers and enumerated options enter a command."""
    p = len(mapping['spec']['x'])
    aliases = [f'n{i+1}' for i in range(p)]
    effects = mapping['effects']
    absorb = 'ec' if 'ec' in effects else 'tc'
    explicit = [f'i.{effect}' for effect in effects if effect != absorb]
    method = mapping['spec']['standard_errors']['method']
    option = {'classical': '', 'hc1': ' vce(robust)', 'cluster': ' vce(cluster cc)'}[method]
    return f"areg n{p+1} {' '.join(aliases+explicit)}, absorb({absorb}){option} level(95)"


def analysis_script(mapping):
    names = ' '.join(mapping['aliases'])
    token = mapping['run_token']
    linear = mapping['spec']['model'] == 'linear_fe'
    lines = ['version 19.0', 'clear all', 'set more off', 'set varabbrev off',
             'set type double', 'set processors 1', 'global S_ADO "BASE"',
             'import delimited "input.csv", clear asdouble',
             'do "helpers.mata"', f'mata: eb_describe("{names}")']
    if linear:
        p = len(mapping['spec']['x'])
        absorb = 'ec' if 'ec' in mapping['effects'] else 'tc'
        explicit = ' '.join(f'i.{e}' for e in mapping['effects'] if e != absorb)
        lines.extend([regression_command(mapping),
                      'matrix eb_b = e(b)', 'matrix eb_V = e(V)',
                      'matrix eb_T = r(table)', '_ms_omit_info eb_b',
                      'matrix eb_O = r(omit)', 'generate byte sample = e(sample)',
                      'mata: eb_matrix("coefficients.csv", st_matrix("eb_b"))',
                      'mata: eb_matrix("covariance.csv", st_matrix("eb_V"))',
                      f'mata: eb_matrix("core_covariance.csv", st_matrix("eb_V")[|1,1\\{p},{p}|])',
                      'mata: eb_matrix("table.csv", st_matrix("eb_T"))',
                      'mata: eb_matrix("omitted.csv", st_matrix("eb_O"))',
                      'mata: eb_stripes()', f'mata: eb_metadata(1, "{token}")',
                      f'quietly areg n{p+1} {explicit}, absorb({absorb})',
                      'mata: eb_matrix("within_y_ss.csv", st_numscalar("e(rss)"))'])
    else:
        lines.extend(['generate byte sample = 1', f'mata: eb_metadata(0, "{token}")'])
    lines.extend(['sort rowid', 'format _all %24.17g',
                  'export delimited rowid ec tc cc '+names+' sample using "roundtrip.csv", replace datafmt',
                  'file open complete using "complete.txt", write replace',
                  f'file write complete "completed:{token}" _n', 'file close complete', 'exit, clear'])
    return ('\n'.join(lines)+'\n').encode('ascii')
