# EditorConfig

## What it is

EditorConfig is a tiny file format, `.editorconfig`, that tells editors how to treat text files: which indentation, which line endings, whether to trim trailing spaces. Most editors read it natively or through a plug-in. It does not run any code.

## Why this repository uses it

Different editors default to different settings. Without a shared file, one person's commit changes every line ending or replaces a Makefile's tabs with spaces, and the diff becomes noise or the build breaks.

## Where it appears

| Path | Use |
|---|---|
| `.editorconfig` | The one file, at the repository root. |

## How it works underneath

The editor looks upward from the file you open for `.editorconfig`. `root = true` stops the search. Section headings (`[*]`, `[*.md]`) are glob patterns; later sections override earlier ones.

## Walkthrough of this repository's use

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4
```
For all files: UTF-8 text, Unix line endings (`lf`), one newline at the end, no trailing spaces, four spaces per indent level.

```ini
[*.{yml,yaml,json,toml}]
indent_size = 2
```
Data files use two spaces. `{a,b}` matches either.

```ini
[Makefile]
indent_style = tab
```
Make requires a real tab at the start of every recipe line ([make.md](make.md)).

```ini
[*.md]
trim_trailing_whitespace = false
```
In Markdown, two trailing spaces mean "line break", so trimming would change the text.

## Try it yourself

```bash
cat .editorconfig
```

```bash
grep -rnP "[ \t]+$" --include="*.py" src scripts | head -3
```
Expect nothing: no Python file has trailing whitespace.

```bash
grep -nP "^ +\S" Makefile | head -3
```
Lines indented with spaces in the Makefile appear here. Expect only the continuation lines of `export` and `.PHONY` (lines 11 and 14); no recipe line may be listed. The same file also governs `template/Makefile`.

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
