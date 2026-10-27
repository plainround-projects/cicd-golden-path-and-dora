# EditorConfig

## What it is

Different text editors have different habits: some indent with tabs, some with spaces; some end lines in the Windows way, some in the Unix way; some leave stray spaces at the ends of lines. When several people (or tools) edit the same files, those habits create noisy changes and, in a few files, real breakage. **EditorConfig** is a small standard: a file named `.editorconfig` at the top of a project tells every editor that supports it how to treat each kind of file. Most editors read it natively or through a plug-in. It does not run anything and it does not check anything; it only guides editors as you type and save.

## Why this repository uses it

Because it fixes things the language tools do not: a `Makefile` *requires* a real tab at the start of each command line ([make.md](make.md)); Markdown uses two trailing spaces to mean "line break", so trailing spaces must not be trimmed there; data files are conventionally indented by two spaces and Python by four. [ruff](ruff.md) enforces Python style in the pipeline; EditorConfig makes the editor do the right thing before the code ever reaches ruff.

## Where it appears

| Path | Use |
|---|---|
| `.editorconfig` | The only file, at the repository root. |

## How it works underneath

An editor looks for `.editorconfig` in the folder of the file you open and in each parent folder, stopping at one that says `root = true`. Inside, a `[pattern]` heading selects files (`*` is any file name, `*.md` Markdown files, `{a,b}` either one) and the `key = value` lines below apply to them. If several sections match, later sections override earlier ones.

## Walkthrough of this repository's use

```
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{yml,yaml,json,toml}]
indent_size = 2

[Makefile]
indent_style = tab

[*.md]
trim_trailing_whitespace = false
```

- **Line 1**: `root = true` says "do not look for more `.editorconfig` files above this one".
- **Line 3**: `[*]` applies to every file. **Line 4**: `charset = utf-8`: text is saved as UTF-8. **Line 5**: `end_of_line = lf`: lines end with the single "line feed" character used on Linux and macOS, never the Windows pair (carriage return plus line feed). **Line 6**: `insert_final_newline = true`: every file ends with a newline, which Unix tools and Git expect. **Line 7**: `trim_trailing_whitespace = true`: remove spaces left at the ends of lines. **Lines 8 and 9**: `indent_style = space` and `indent_size = 4`: indent with four spaces.
- **Line 11**: `[*.{yml,yaml,json,toml}]` applies to YAML, JSON and TOML files; **line 12**: `indent_size = 2`: two spaces, the convention in those formats ([yaml.md](yaml.md), [toml.md](toml.md), [json.md](json.md)).
- **Lines 14 and 15**: `[Makefile]` with `indent_style = tab`: a Makefile's command lines must start with a tab character, not spaces. Without this, an editor might convert them and `make` would stop with `*** missing separator`.
- **Lines 17 and 18**: `[*.md]` with `trim_trailing_whitespace = false`: in Markdown two trailing spaces mean "break the line here", so trimming them would change the document ([markdown.md](markdown.md)).

## Try it yourself

```bash
cat .editorconfig
```

```bash
grep -rnP "[ \t]+$" --include="*.py" src pipeline | head -3
```
Expect nothing: no Python file has trailing whitespace.

```bash
grep -nP "^ +\S" Makefile | head -3
```
Lines indented with spaces in the Makefile appear here. Expect only the continuation line of `.PHONY` (line 12); no recipe line may be listed.

## Mistakes people make

- Assuming it is enforced. It only guides editors; [ruff](ruff.md) enforces Python style in the pipeline.
- Forgetting `root = true`, so a stray file higher up changes the rules.
- Letting an editor convert tabs in a Makefile.

## Check yourself

1. Does EditorConfig run in CI? *No; editors read it.*
2. Why does the Makefile section say `indent_style = tab`? *Make requires tabs on recipe lines.*
3. Why do Markdown files keep trailing spaces? *Two trailing spaces can be a line break.*
4. What does `end_of_line = lf` do? *Uses Unix line endings.*
5. What does `root = true` do? *Stops the search for parent configuration files.*

## Further reading

- EditorConfig specification: https://spec.editorconfig.org/ and https://editorconfig.org/
