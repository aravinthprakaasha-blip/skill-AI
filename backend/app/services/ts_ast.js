// AST analyzer for JavaScript/TypeScript using the TypeScript compiler API.
// Used when the Tree-sitter native binding cannot be loaded. Reads source from stdin,
// banned lists from argv[3] (JSON), prints one JSON report to stdout.
"use strict";
const ts = require(process.argv[2]);
const banned = JSON.parse(process.argv[3]);
const lang = process.argv[4];
const code = require("fs").readFileSync(0, "utf8");

const sf = ts.createSourceFile("main." + (lang === "typescript" ? "ts" : "js"), code, ts.ScriptTarget.Latest, true,
  lang === "typescript" ? ts.ScriptKind.TS : ts.ScriptKind.JS);
const K = ts.SyntaxKind;
const line = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
const endLine = (n) => sf.getLineAndCharacterOfPosition(n.getEnd()).line + 1;
const violations = [], imports = [], features = new Set(), functions = [], classes = [];
const MAPS = new Set(["Map", "WeakMap", "Object"]), SETS = new Set(["Set", "WeakSet"]);
const LOOPS = new Set([K.ForStatement, K.ForInStatement, K.ForOfStatement, K.WhileStatement, K.DoStatement]);
const BRANCH = new Set([...LOOPS, K.IfStatement, K.CaseClause, K.ConditionalExpression, K.CatchClause]);
const NEST = new Set([...LOOPS, K.IfStatement, K.TryStatement, K.SwitchStatement]);
const v = (rule, message, ln) => violations.push({ rule, message, line: ln });

const diags = sf.parseDiagnostics || [];
if (diags.length) v("syntax", "Syntax error: " + ts.flattenDiagnosticMessageText(diags[0].messageText, " "),
  sf.getLineAndCharacterOfPosition(diags[0].start || 0).line + 1);

function fnName(n) {
  if (n.name && n.name.getText) return n.name.getText(sf);
  const p = n.parent;
  if (p && (ts.isVariableDeclaration(p) || ts.isPropertyAssignment(p) || ts.isPropertyDeclaration(p)) && p.name) return p.name.getText(sf);
  return "<anonymous>";
}
function walk(n, f) { f(n); ts.forEachChild(n, (c) => walk(c, f)); }
function depth(n, d) {
  let best = d;
  ts.forEachChild(n, (c) => { best = Math.max(best, depth(c, d + (NEST.has(c.kind) ? 1 : 0))); });
  return best;
}
const isFn = (n) => ts.isFunctionDeclaration(n) || ts.isMethodDeclaration(n) || ts.isArrowFunction(n) || ts.isFunctionExpression(n) || ts.isConstructorDeclaration(n);
const LIT = new Set([K.NumericLiteral, K.StringLiteral, K.TrueKeyword, K.FalseKeyword, K.NullKeyword, K.ArrayLiteralExpression, K.NoSubstitutionTemplateLiteral]);

walk(sf, (n) => {
  const ln = () => line(n);
  if (ts.isImportDeclaration(n)) {
    const src = n.moduleSpecifier.text; imports.push(src);
    if (banned.imports.includes(src) || src.startsWith("node:")) v("banned_import", "Import of `" + src + "` is not allowed", ln());
  } else if (ts.isCallExpression(n)) {
    const callee = n.expression;
    const name = ts.isIdentifier(callee) ? callee.text : (ts.isPropertyAccessExpression(callee) ? callee.name.text : "");
    if (ts.isIdentifier(callee) && banned.calls.includes(name)) v("banned_call", "Call to `" + name + "()` is not allowed", ln());
    if (name === "sort") features.add("builtin_sort");
  } else if (ts.isNewExpression(n)) {
    const c = n.expression.getText(sf);
    if (MAPS.has(c)) features.add("dict");
    if (SETS.has(c)) features.add("set");
    if (banned.calls.includes(c) || banned.names.includes(c)) v("banned_call", "`new " + c + "` is not allowed", ln());
  } else if (ts.isIdentifier(n) && banned.names.includes(n.text)) {
    const p = n.parent;
    const isProp = p && ts.isPropertyAccessExpression(p) && p.name === n;
    if (!isProp) v("banned_name", "Use of `" + n.text + "` is not allowed", ln());
  } else if (ts.isObjectLiteralExpression(n) && n.parent && (ts.isVariableDeclaration(n.parent) || ts.isBinaryExpression(n.parent))) {
    features.add("dict");
  } else if (LOOPS.has(n.kind)) features.add("loop");
  else if (ts.isTryStatement(n)) features.add("try_except");
  else if (ts.isThrowStatement(n)) features.add("raise");
  else if (ts.isClassDeclaration(n) || ts.isClassExpression(n)) {
    features.add("class");
    classes.push({ name: n.name ? n.name.text : "<anonymous>", line: ln(),
      methods: n.members.filter((m) => ts.isMethodDeclaration(m)).map((m) => m.name.getText(sf)) });
  }
  if (isFn(n)) {
    const name = ts.isConstructorDeclaration(n) ? "constructor" : fnName(n);
    const calls = new Set(), loops = [], returns = [];
    let cx = 1, computes = false;
    walk(n, (c) => {
      if (ts.isCallExpression(c)) {
        const e = c.expression;
        calls.add(ts.isIdentifier(e) ? e.text : (ts.isPropertyAccessExpression(e) ? e.name.text : ""));
      }
      if (LOOPS.has(c.kind)) { loops.push(c); computes = true; }
      if (BRANCH.has(c.kind)) cx++;
      if (ts.isBinaryExpression(c)) {
        const op = c.operatorToken.kind;
        if (op === K.AmpersandAmpersandToken || op === K.BarBarToken) cx++;
        if (![K.EqualsEqualsEqualsToken, K.EqualsEqualsToken, K.ExclamationEqualsEqualsToken, K.ExclamationEqualsToken, K.EqualsToken].includes(op)) computes = true;
      }
      if (ts.isPrefixUnaryExpression(c) || ts.isPostfixUnaryExpression(c)) computes = true;
      if (ts.isReturnStatement(c)) returns.push(c);
    });
    calls.delete("");
    const recursive = name !== "<anonymous>" && calls.has(name);
    if (recursive) features.add("recursion");
    const lit = returns.filter((r) => r.expression && LIT.has(r.expression.kind));
    if (name !== "<anonymous>" && returns.length >= 2 && lit.length === returns.length && !computes && calls.size === 0)
      v("hardcoded_output", "`" + name + "` returns hardcoded values instead of computing a result", ln());
    if (name !== "<anonymous>") functions.push({
      name, line: ln(), end_line: endLine(n), params: n.parameters.map((p) => p.name.getText(sf)),
      complexity: cx, recursive, loops: loops.length,
      loop_kinds: [...new Set(loops.map((l) => K[l.kind].replace("Statement", "").toLowerCase()))].sort(),
      calls: [...calls].sort().slice(0, 12), has_docstring: false,
    });
  }
});
const loc = code.split("\n").filter((l) => l.trim() && !/^\s*(\/\/|\*|\/\*)/.test(l)).length;
functions.sort((a, b) => a.line - b.line);
process.stdout.write(JSON.stringify({
  parse_ok: diags.length === 0, violations, features: [...features].sort(), functions, classes,
  imports: [...new Set(imports)].sort(),
  metrics: { loc, functions: functions.length, classes: classes.length,
    max_complexity: Math.max(1, ...functions.map((f) => f.complexity)), max_nesting: depth(sf, 0) },
}));
