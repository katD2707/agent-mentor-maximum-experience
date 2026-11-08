/**
 * Single-variable expression parser for `function_plot` diagrams (port of agent-mentor `Expression.kt`).
 * Grammar, explicit multiplication only:
 *   expr := term (('+'|'-') term)*   term := unary (('*'|'/') unary)*   unary := '-' unary | power
 *   power := atom ('^' unary)?       atom := number | x | pi | e | func '(' expr ')' | '(' expr ')'
 * Functions: sin cos tan exp ln log (base 10) sqrt abs. Never uses eval/Function.
 */

export type Expr = (x: number) => number;

export class ExprError extends Error {
  readonly position: number;
  constructor(message: string, position: number) {
    super(message);
    this.name = "ExprError";
    this.position = position;
  }
}

const FUNCS: Record<string, (v: number) => number> = {
  sin: Math.sin,
  cos: Math.cos,
  tan: Math.tan,
  exp: Math.exp,
  ln: Math.log,
  log: Math.log10,
  sqrt: Math.sqrt,
  abs: Math.abs,
};

export function parseExpr(src: string): Expr {
  let pos = 0;
  const fail = (m: string): never => {
    throw new ExprError(`${m} at ${pos} in "${src}"`, pos);
  };
  const ws = () => {
    while (pos < src.length && /\s/.test(src[pos])) pos++;
  };
  const eat = (c: string): boolean => {
    ws();
    if (src[pos] === c) {
      pos++;
      return true;
    }
    return false;
  };
  const expect = (c: string) => {
    if (!eat(c)) fail(`Expected '${c}'`);
  };

  function expr(): Expr {
    let left = term();
    for (;;) {
      if (eat("+")) {
        const l = left;
        const r = term();
        left = (x) => l(x) + r(x);
      } else if (eat("-")) {
        const l = left;
        const r = term();
        left = (x) => l(x) - r(x);
      } else return left;
    }
  }
  function term(): Expr {
    let left = unary();
    for (;;) {
      if (eat("*")) {
        const l = left;
        const r = unary();
        left = (x) => l(x) * r(x);
      } else if (eat("/")) {
        const l = left;
        const r = unary();
        left = (x) => l(x) / r(x);
      } else {
        ws();
        if (pos < src.length && /[A-Za-z0-9(]/.test(src[pos])) fail("Implicit multiplication is not supported; write '*'");
        return left;
      }
    }
  }
  function unary(): Expr {
    ws();
    if (eat("-")) {
      const inner = unary();
      return (x) => -inner(x);
    }
    if (eat("+")) return unary();
    return power();
  }
  function power(): Expr {
    const base = atom();
    if (eat("^")) {
      const exp = unary();
      return (x) => Math.pow(base(x), exp(x));
    }
    return base;
  }
  function atom(): Expr {
    ws();
    if (pos >= src.length) return fail("Unexpected end of expression");
    if (eat("(")) {
      const inner = expr();
      expect(")");
      return inner;
    }
    const c = src[pos];
    if (/[0-9.]/.test(c)) {
      const start = pos;
      while (pos < src.length && /[0-9.]/.test(src[pos])) pos++;
      const v = Number(src.slice(start, pos));
      if (!Number.isFinite(v)) return fail("Bad number");
      return () => v;
    }
    if (/[A-Za-z]/.test(c)) {
      const start = pos;
      while (pos < src.length && /[A-Za-z]/.test(src[pos])) pos++;
      const name = src.slice(start, pos);
      if (name === "x") return (x) => x;
      if (name === "pi") return () => Math.PI;
      if (name === "e") return () => Math.E;
      const f = FUNCS[name];
      if (!f) return fail(`Unknown identifier '${name}'`);
      expect("(");
      const arg = expr();
      expect(")");
      return (x) => f(arg(x));
    }
    return fail(`Unexpected '${c}'`);
  }

  const e = expr();
  ws();
  if (pos !== src.length) fail(`Unexpected '${src[pos]}'`);
  return e;
}
