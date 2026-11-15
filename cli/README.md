# twelveswaras

Name the raaga in a recording of Carnatic or Hindustani music, and look up the 70 raagas
[twelveswaras](https://twelveswaras.com) knows. A command line and a local MCP server in one package.
Node 18+, no dependencies.

```bash
npx -y twelveswaras identify concert.m4a
```

```
Most likely: Kalyāṇi
   75%  Kalyāṇi (carnatic)           https://twelveswaras.com/raaga/kalyani
    8%  Kāmavardani (carnatic)       https://twelveswaras.com/raaga/kamavardani
    7%  Śankarābharaṇaṁ (carnatic)   https://twelveswaras.com/raaga/sankarabharanam
Tonic (Sa): 117 Hz. Heard 150 s.
```

## Commands

| Command | What it does |
|---|---|
| `twelveswaras identify <file\|->` | The three likeliest raagas with confidence, the tonic (Sa) it heard, and each raaga's page. mp3, m4a, wav, ogg or webm, up to 25 MB; `-` reads stdin. |
| `twelveswaras raaga <name>` | A raaga in any spelling (Mohanam, Mōhanaṁ, Bhoop, "kalyani ragam"): scale, parent, notes, how to hear it, songs, page. |
| `twelveswaras notes "S R2 G3 P D2"` | The raagas whose scale is exactly these notes, and those that use them and more. Carnatic labels or Hindustani letters (`S r R g G m M P d D n N`: lowercase komal, `M` tivra). |
| `twelveswaras list` | The 70 raagas, with tradition and page. |
| `twelveswaras serve` | The MCP server on stdio (also what it does with no arguments, when not on a terminal). |

Options:

- `--tradition carnatic|hindustani`: raaga, notes and list in one tradition only.
- `--from mm:ss`: identify from that point, for a recording that opens with applause or talk, or one
  over 25 MB. Cuts 5 minutes there with [ffmpeg](https://ffmpeg.org), which must be on your PATH.
- `--json`: the result as JSON (identify gives the same shape as the MCP tool `identify_raaga`).
- `--format md`: a markdown document with the CC-BY credit, ready to share.
- `--share`: posts that markdown with `npx -y mdshare-mcp upload -` and prints the link. The
  document's key stays in mdshare-mcp's own store (`mdshare-mcp ls` lists it).
- `-o <file>`: write the result to a file.
- `--help` on any command; `--version`.

Results go to stdout, progress and errors to stderr. Exit codes: 0 ok, 1 failure (network, the
site, an unknown raaga), 2 bad usage (a missing or oversized file, `--from` without ffmpeg).

## How it listens

The recording is uploaded to twelveswaras.com, analysed, and not stored. The recognizer hears the
first 5 minutes (the melody's first 150 s), so a whole concert is fine: it is judged from its start,
or from `--from`. A minute or more with a tanpura or drone works best. On real recordings the top
answer is right about 71% of the time and the right raaga is in the top three about 80% of the time;
when it is not sure, it says so.

Each identification is counted once on the site, as a browser listen is (the raaga names, the
tonic and how long it heard; never the audio or the file name). Requests carry the User-Agent
`twelveswaras-cli/<version>`. The site allows each address 100 identifications in ten minutes.

## As an MCP server

With no arguments it is a stdio MCP server with the same four tools as the hosted server at
`https://twelveswaras.com/mcp` (`find_raaga`, `raagas_with_notes`, `list_raagas`, `identify_raaga`),
which it calls. One difference: here `identify_raaga` also takes `path`, a recording on this
machine (and `from`), as well as a public `audio_url`.

```json
{ "mcpServers": { "twelveswaras": { "command": "npx", "args": ["-y", "twelveswaras"] } } }
```

## Credit and licence

Raaga data and results: twelveswaras (twelveswaras.com), CC-BY-4.0. Code: MIT. Source:
[github.com/twelveswaras/twelveswaras](https://github.com/twelveswaras/twelveswaras) (`cli/`).
