# trlabel

**Label every hop of a traceroute with the router it belongs to.**

A traceroute gives you a column of IP addresses. To understand the path you then
have to work out which router each address lives on. `trlabel` does that lookup
for you: paste in the traceroute, and it matches each hop against your own
interface/IP inventory exports (Nokia and Huawei CSVs) and prints the router
name and interface next to every IP.

- **Zero dependencies.** Single file, Python standard library only.
- **Runs on Python 2.7 and Python 3.** Built for locked-down, offline Linux hosts where you can't `pip install` anything.
- **Zero config.** Drop the script and your CSV exports in one folder. They're picked up automatically.
- **Handles messy vendor exports.** Preamble lines before the header, IP and mask in separate columns, rows with no IP, CRLF line endings, BOMs.
- **Duplicate-aware.** If one IP exists on several devices, every device is listed with its interface and the file it came from.

## Example

```text
$ python trlabel.py
Paste traceroute output, then press Ctrl+D:
 1 10.10.1.2  4 ms  3 ms  4 ms
 2 10.10.2.6  6 ms  4 ms  4 ms
 3 * * *
 4 10.10.3.9  5 ms  3 ms  3 ms
 5 10.10.4.1  3 ms  2 ms  2 ms
^D

hop  ip         router                interface      source
1    10.10.1.2  CORE-HW-01            GE0/2/1        huawei_interfaces.csv
2    10.10.2.6  peer of CORE-HW-01    GE0/2/1        huawei_interfaces.csv
3    *          (no response)
4    10.10.3.9  EDGE-NOK-07           to-core-lag-1  nokia_interfaces.csv
5    10.10.4.1  !! 2 DEVICES SHARE THIS IP
      - EDGE-NOK-07  |  mgmt-vm  |  nokia_interfaces.csv
      - EDGE-NOK-09  |  mgmt-vm  |  nokia_interfaces.csv
```

(All names and addresses above are fictional.)

## Quick start

```text
trlabel/
├── trlabel.py
├── huawei_interfaces.csv     <- your exports, any file name, must end in .csv
└── nokia_interfaces.csv
```

```bash
# paste a traceroute (finish with Ctrl+D)
python trlabel.py

# or look up one or more IPs directly
python trlabel.py 10.10.1.2 10.10.2.6

# or read a saved traceroute from a file
python trlabel.py -f hops.txt

# machine-readable output
python trlabel.py -f hops.txt --csv > labelled.csv
```

Handy alias, since the script finds its CSVs next to itself and works from any directory:

```bash
alias trl='python ~/trlabel/trlabel.py'
```

## How it works

1. **Load.** Every `*.csv` in the script's folder is read. For each file the script
   finds the real header row (skipping any preamble), then detects the IP, device
   name, interface and mask columns from the header names. It prints what it
   picked, so you can check it.
2. **Parse your input.** Paste a whole traceroute, prompt lines and all, or a
   plain list of IPs. If numbered hop lines are present, only those are read, so
   command echoes and `traceroute to ...` banners can't create fake hops.
3. **Look up.** For each hop IP:
   - **Exact match:** the IP is on a known interface. The output shows that router and interface.
   - **`peer of ROUTER`:** the IP isn't in your inventory, but sits on the same `/30` or `/31` link as one of `ROUTER`'s interfaces. It's the device at the other end of that link, which is useful for spotting where traffic leaves your network.
   - **`!! N DEVICES SHARE THIS IP`:** the same IP appears on more than one device. Each is listed with interface and source file.
   - **`UNKNOWN`:** not in any CSV.
   - **`(no response)`:** a `* * *` hop.

One router with the same IP on several interfaces (for example a management
address repeated across sub-interfaces) is **not** treated as a duplicate. It's
one router, with the interfaces listed.

### What the label means

Routers normally answer a traceroute probe from the interface the probe **entered
on**. So each label reads as "the router this packet just reached, and the
interface it came in on". The router you ran the traceroute from never appears,
and the final hop is often a loopback or end device that may not be in your
inventory.

## Input CSV requirements

Nothing needs renaming, but each CSV must contain at minimum:

| Needed | Detected from headers such as |
|---|---|
| Device name | `NE Name`, `Site Name`, `Hostname`, `Sysname`, `Device`, `Node`, `Router` |
| IP address | `IPv4 Address`, `IP Address`, `IP` |
| Interface (optional) | `Interface Name`, `Interface`, `Port` |
| Mask / prefix (optional) | `IPv4 Address Mask`, `Prefix Length`, `Mask` |

- A mask given as dotted decimal (`255.255.255.254`) or as a prefix length (`31`) both work, as does `10.0.0.1/31` directly in the IP cell.
- **Without a mask**, exact matches still work, but the `peer of` lookup can't.
- Extra address columns named `Site ID`, `System IP`, `System Address`, `Router ID`, `Node IP`, `Management IP` or `LSRID` are indexed too (system/loopback addresses are common reply sources).
- Rows with no IP (`-`, `--`, blank) are skipped automatically. You don't need to pre-filter the exports.
- Delimiters `,`  `;` and tab are auto-detected.

If a future export renames a column, override the detection (see options below).

## Options

| Option | Description |
|---|---|
| `IP ...` | One or more IPs to look up |
| `-f`, `--file FILE` | Read traceroute output from a file |
| *(no input given)* | Read from the terminal. Paste, then press Ctrl+D |
| `--data-dir DIR` | Load CSVs from `DIR` instead of the script's folder |
| `--max-dups N` | Devices listed under a duplicate IP (default 8) |
| `--all` | List every device for duplicate IPs |
| `--csv` | CSV output, one row per matching device |
| `--ip-col`, `--host-col`, `--if-col`, `--mask-col` | Force a column by exact header text |
| `--stats` | Per-file summary and integrity check (no traceroute needed) |
| `--grep TEXT` | Show rows containing `TEXT` in any column of any CSV |
| `--limit N` | Max rows shown by `--grep` (default 20) |

## Diagnostics

Getting `UNKNOWN` for an IP you expected to find? Check the data before
suspecting the tool.

```bash
python trlabel.py --stats
```

```text
inventory.csv  (header on line 8)
  data rows               : 19993
  header claims           : 193308 records   <-- FILE HAS FEWER ROWS THAN IT CLAIMS
  short/broken rows       : 0
  blank or '-' device name: 0
  rows WITH an IPv4       : 8574   (these get indexed)
  rows without an IPv4    : 11419  (blank or '-': 11419, other text: 0)
  distinct devices        : 1204   (610 have at least one IPv4)
```

```bash
python trlabel.py --grep 10.10.2.     # is this subnet anywhere in the data?
python trlabel.py --grep CORE-HW-01   # is this device in the exports at all?
```

If an export states a total (`Total N Records`) and the file has noticeably
fewer rows, the tool warns at load time. Management systems often cap CSV
exports at a fixed row count (for example 20,000), so a big inventory can be
silently truncated. When that happens, devices missing from the export show as
`UNKNOWN`. The fix is a complete export (filter and export in batches), not a
code change. All CSVs in the folder are merged, so batches can simply sit side
by side.

## Limitations

- **IPv4 only.**
- **No VRF awareness.** If the same address exists in different VRFs, all matches are listed as duplicates. Check which VRF you traced in.
- **Only as good as your exports.** Stale or incomplete inventory gives stale or missing labels.
- **`peer of` needs `/30` or `/31` masks** in the inventory for that link.
- Python 2.7 is end-of-life. It's supported here only because some production hosts still ship it.

## Keep your inventory out of Git

Interface/IP exports describe your network's topology. **Don't commit them**,
especially to a public repository. Add this to `.gitignore`:

```gitignore
*.csv
*.txt
labelled*.csv
```

and use only fictional data in examples and issues.

## Compatibility

Tested on CPython 2.7.18 and 3.12 (identical output), and in day-to-day use on a
Linux host running Python 2.7.5 with no internet access.

## License

MIT. See `LICENSE`.
