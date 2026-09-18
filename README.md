# code-checker

The sweep that was run across every repository on this account on
18 September 2026, kept so it can be run again.

`AUDIT-2026-09-18.md` is what that sweep found. `patches/` holds the fixes as
`git format-patch` files, one per repository. `checks/` holds the tools.

## Run it again

Point the scripts at a directory holding the clones, or at a single repo.

```sh
checks/check-syntax.sh  ~/code     # parse every source file; exits 1 on a failure
checks/scan-secrets.sh  ~/code     # credentials and runtime state committed to git
```

`check-syntax.sh` covers Python, JavaScript (script and module), inline
`<script>` blocks inside HTML, shell scripts, and local `src`/`href`
references that point at files which do not exist. It needs `python3`,
`node` and `bash`, nothing else.

The two helpers are usable on their own:

```sh
node checks/check-inline-scripts.js page.html   # parse each inline <script>
node checks/dead-refs.js            page.html   # find broken local src/href
node checks/extract-inline-scripts.js page.html OUTDIR
```

`extract-inline-scripts.js` pulls a page's inline scripts into real files so a
linter can see them: classic scripts become one `classic.js`, because that is
the scope the browser gives them, and each `type="module"` script becomes its
own `.mjs`. It also writes a `meta.json` recording which globals the page's
`<script src>` tags provide, so a linter does not report Leaflet's `L` or
Three's `THREE` as undefined, and a line map so findings can be reported
against the HTML rather than the extracted file.

## Applying a patch

```sh
cd ~/code/vault-brain && git am < ~/code/code-checker/patches/vault-brain.patch
```

`patches/jarvis.patch` is the one exception: it carries only the `.gitignore`
change, and the file says which `git rm --cached` to run by hand. Its commit
also removed a 4 MB SQLite write-ahead log, and embedding that in a patch
would have re-published the rows the fix exists to remove.
