"""GBNF that forces the CoT cycle to emit a JSON object (no prose wrapper)."""

REASONING_JSON_GBNF = r"""
root   ::= object
object ::= "{" ws members? ws "}"
members ::= pair (ws "," ws pair)*
pair    ::= string ws ":" ws value
array  ::= "[" ws (value (ws "," ws value)*)? ws "]"
value  ::= object | array | string | number | "true" | "false" | "null"
string ::= "\"" char* "\""
char   ::= [^"\\] | "\\" (["\\] | "n" | "t" | "/")
number ::= "-"? ("0" | [1-9] [0-9]*) ("." [0-9]+)? ([eE] [+-]? [0-9]+)?
ws     ::= [ \t\n]*
"""
