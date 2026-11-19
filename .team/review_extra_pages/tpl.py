import json
def split(s):
    a = 'const PAGE_TEMPLATE = '
    i = s.index(a) + len(a); j = s.index(';\n', i)
    return i, j
def enc(t):
    return json.dumps(t, ensure_ascii=False, separators=(',', ':')).replace('<', chr(92) + 'u003c')
if __name__ == '__main__':
    s = open('liberty_offense_defense.html', encoding='utf-8', newline='').read()
    i, j = split(s); lit = s[i:j]; t = json.loads(lit); r = enc(t)
    print('exact', r == lit)
    if r != lit:
        n = next(k for k in range(min(len(r), len(lit))) if r[k] != lit[k]); print(n, repr(lit[max(0,n-30):n+30])); print(repr(r[max(0,n-30):n+30]))
