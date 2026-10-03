#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
trlabel.py - label traceroute hops with router names from your interface CSVs.
Works on Python 2.7 and Python 3. Standard library only.
All *.csv files in the same folder as this script are loaded.

Usage:
  python trlabel.py 10.251.181.6 10.251.240.158   # one or more IPs
  python trlabel.py -f hops.txt                   # file with traceroute output
  python trlabel.py                               # paste output, then Ctrl+D

Options:
  --data-dir DIR    look for CSVs somewhere else
  --max-dups N      max devices listed under a duplicate IP (default 8)
  --all             list every device for duplicate IPs
  --csv             CSV output (one row per matching device)
  --ip-col / --host-col / --if-col / --mask-col   override column detection
"""
from __future__ import print_function

import argparse
import csv
import glob
import os
import re
import sys

PY3 = sys.version_info[0] >= 3

IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?\b")
IPV4_FULL = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?$")
IP_EXCLUDE = ("ipv6", "type", "mask", "prefix", "status", "operating", "enable")
HOST_EXACT = ("ne name", "site name", "hostname", "host name", "sysname", "sys name",
              "device name", "device", "node name", "node", "router name", "router", "system name")
EXTRA_IP_EXACT = ("site id", "system ip", "system address", "router id", "node ip",
                  "management ip", "mgmt ip", "lsrid")


# ---------- IPv4 helpers (no ipaddress module on py2) ----------
def ip2int(s):
    parts = s.split(".")
    if len(parts) != 4:
        return None
    n = 0
    for p in parts:
        if not p.isdigit():
            return None
        v = int(p)
        if v > 255:
            return None
        n = (n << 8) | v
    return n


def plen_mask(plen):
    return (0xFFFFFFFF << (32 - plen)) & 0xFFFFFFFF


def parse_addr(ip, mask):
    """Return (int_ip, prefixlen) or None."""
    n = ip2int(ip)
    if n is None:
        return None
    plen = 32
    mask = (mask or "").strip()
    if mask:
        if re.match(r"^\d{1,2}$", mask):
            if int(mask) <= 32:
                plen = int(mask)
        elif IPV4_FULL.match(mask):
            m = ip2int(mask)
            if m is not None:
                p = bin(m).count("1")
                if m == plen_mask(p):
                    plen = p
    return n, plen


# ---------- column detection ----------
def norm(h):
    return re.sub(r"\s+", " ", h.strip().lower())


def find_ip(headers):
    n = [norm(h) for h in headers]
    for want in ("ipv4 address", "ip address", "ipv4", "ip"):
        for i, h in enumerate(n):
            if h == want:
                return i
    for i, h in enumerate(n):
        if re.search(r"\bip", h) and not any(x in h for x in IP_EXCLUDE):
            return i
    return None


def find_host(headers):
    n = [norm(h) for h in headers]
    for want in HOST_EXACT:
        for i, h in enumerate(n):
            if h == want:
                return i
    for i, h in enumerate(n):
        if any(k in h for k in ("host", "sysname", "device", "router", "node")):
            return i
    for i, h in enumerate(n):
        if "name" in h and not any(x in h for x in ("interface", "port", "description", "user")):
            return i
    return None


def find_if(headers):
    n = [norm(h) for h in headers]
    for want in ("interface name", "interface", "ifname", "port"):
        for i, h in enumerate(n):
            if h == want:
                return i
    for i, h in enumerate(n):
        if "interface" in h and "type" not in h and "status" not in h:
            return i
    return None


def find_mask(headers):
    n = [norm(h) for h in headers]
    for i, h in enumerate(n):
        if ("mask" in h or "prefix length" in h or h == "prefix") and "ipv6" not in h:
            return i
    return None


def resolve(headers, override, finder):
    if override:
        for i, h in enumerate(headers):
            if norm(h) == norm(override):
                return i
        return None
    return finder(headers)


# ---------- loading ----------
def open_csv(path):
    if PY3:
        return open(path, newline="", encoding="utf-8-sig", errors="replace")
    return open(path, "rb")


def strip_bom(lines):
    first = True
    for ln in lines:
        if first:
            first = False
            if ln.startswith("\xef\xbb\xbf"):
                ln = ln[3:]
        yield ln


def add(exact, links, n, plen, host, ifname, src):
    lst = exact.setdefault(n, [])
    for e in lst:
        if e[0] == host and e[1] == ifname:
            if src not in e[2].split(","):
                e[2] += "," + src
            break
    else:
        lst.append([host, ifname, src])
    if plen in (30, 31):
        links.setdefault((n & plen_mask(plen), plen), []).append((n, host, ifname, src))


def nm(headers, i):
    return "'%s'" % headers[i] if i is not None else "-"


def load_file(path, exact, links, ov):
    name = os.path.basename(path)
    for delim in (",", ";", "\t"):
        cols, count, headers = None, 0, None
        f = open_csv(path)
        try:
            for row in csv.reader(f if PY3 else strip_bom(f), delimiter=delim):
                if cols is None:
                    if len(row) < 3:
                        continue
                    ic = resolve(row, ov["ip"], find_ip)
                    hc = resolve(row, ov["host"], find_host)
                    if ic is None or hc is None:
                        continue
                    nc = resolve(row, ov["if"], find_if)
                    mc = resolve(row, ov["mask"], find_mask)
                    extras = [i for i, h in enumerate(row) if norm(h) in EXTRA_IP_EXACT and i != ic]
                    headers = row
                    cols = (ic, hc, nc, mc, extras)
                    print("[load] %s: ip=%s mask=%s host=%s interface=%s extra-ip=%s" % (
                        name, nm(headers, ic), nm(headers, mc), nm(headers, hc), nm(headers, nc),
                        [headers[i].strip() for i in extras]), file=sys.stderr)
                    continue
                ic, hc, nc, mc, extras = cols
                if len(row) <= max(ic, hc):
                    continue
                host = row[hc].strip()
                if not host or host in ("-", "--"):
                    continue
                ifname = row[nc].strip() if nc is not None and nc < len(row) else ""
                mask = row[mc] if mc is not None and mc < len(row) else ""
                for m in IPV4.finditer(row[ic]):
                    pa = parse_addr(m.group(1), m.group(2) or mask)
                    if pa:
                        add(exact, links, pa[0], pa[1], host, ifname, name)
                        count += 1
                for xc in extras:
                    if xc < len(row):
                        mm = IPV4_FULL.match(row[xc].strip())
                        if mm:
                            pa = parse_addr(mm.group(1), "")
                            if pa:
                                add(exact, links, pa[0], 32, host, "[%s]" % headers[xc].strip(), name)
                                count += 1
        finally:
            f.close()
        if cols is not None:
            print("       %s: %d addresses indexed" % (name, count), file=sys.stderr)
            return True
    print("[skip] %s: no header row with IP + host columns found" % name, file=sys.stderr)
    return False


# ---------- lookup ----------
def lookup(ip, exact, links):
    n = ip2int(ip)
    if n is None:
        return "", []
    if n in exact:
        return "", [tuple(e) for e in exact[n]]
    out = []
    for plen in (31, 30):
        net = n & plen_mask(plen)
        if plen == 30 and (n == net or n == net + 3):
            continue
        for owner, h, i, s in links.get((net, plen), []):
            if owner != n:
                out.append((h, i, s))
    return ("peer of ", out) if out else ("", [])


def group(matches):
    d, order = {}, []
    for h, i, s in matches:
        if h not in d:
            d[h] = {"ifs": [], "srcs": []}
            order.append(h)
        e = d[h]
        if i and i not in e["ifs"]:
            e["ifs"].append(i)
        for x in s.split(","):
            if x not in e["srcs"]:
                e["srcs"].append(x)
    return [(h, d[h]) for h in order]


def short_ifs(ifs, n=3):
    s = ", ".join(ifs[:n])
    if len(ifs) > n:
        s += " (+%d)" % (len(ifs) - n)
    return s


def read_text(path):
    if PY3:
        with open(path, errors="replace") as f:
            return f.read().splitlines()
    with open(path) as f:
        return f.read().splitlines()


def main():
    here = os.path.dirname(os.path.realpath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ips", nargs="*")
    ap.add_argument("-f", "--file")
    ap.add_argument("--data-dir", default=here)
    ap.add_argument("--max-dups", type=int, default=8)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--csv", action="store_true")
    ap.add_argument("--ip-col")
    ap.add_argument("--host-col")
    ap.add_argument("--if-col")
    ap.add_argument("--mask-col")
    a = ap.parse_args()
    ov = {"ip": a.ip_col, "host": a.host_col, "if": a.if_col, "mask": a.mask_col}

    exact, links, loaded = {}, {}, 0
    for p in sorted(glob.glob(os.path.join(a.data_dir, "*.csv"))):
        if load_file(p, exact, links, ov):
            loaded += 1
    if not loaded:
        sys.exit("No usable CSVs found in %s" % a.data_dir)

    if a.ips:
        lines = ["- " + ip for ip in a.ips]
    elif a.file:
        lines = read_text(a.file)
    else:
        if sys.stdin.isatty():
            print("Paste traceroute output, then press Ctrl+D:", file=sys.stderr)
        lines = sys.stdin.read().splitlines()

    hop_re = re.compile(r"^\s*(\d+)\s")
    has_hops = any(hop_re.match(l) for l in lines)
    results = []   # (hop, ip, prefix, grouped)
    for line in lines:
        s = line.strip()
        if not s:
            continue
        hop_m = hop_re.match(line)
        if has_hops and not hop_m:
            continue
        if not has_hops and s.lower().startswith(("traceroute", "tracing", "trace complete", "over a max")):
            continue
        hop = hop_m.group(1) if hop_m else "-"
        seen = set()
        for m in IPV4.finditer(s):
            ip = m.group(1)
            if ip in seen or ip2int(ip) is None:
                continue
            seen.add(ip)
            prefix, matches = lookup(ip, exact, links)
            results.append((hop, ip, prefix, group(matches)))
        if hop_m and not seen and "*" in s:
            results.append((hop, "*", "", None))

    if a.csv:
        w = csv.writer(sys.stdout, lineterminator="\n")
        w.writerow(["hop", "ip", "router", "interface", "source", "devices_for_ip"])
        for hop, ip, prefix, g in results:
            if g is None:
                w.writerow([hop, ip, "(no response)", "", "", 0])
            elif not g:
                w.writerow([hop, ip, "UNKNOWN", "", "", 0])
            else:
                for h, e in g:
                    w.writerow([hop, ip, prefix + h, "; ".join(e["ifs"]), "; ".join(e["srcs"]), len(g)])
        return

    main_rows, details = [], []
    for hop, ip, prefix, g in results:
        det = []
        if g is None:
            row = (hop, ip, "(no response)", "", "")
        elif not g:
            row = (hop, ip, "UNKNOWN", "", "")
        elif len(g) == 1:
            h, e = g[0]
            row = (hop, ip, prefix + h, short_ifs(e["ifs"]), ", ".join(e["srcs"]))
        else:
            label = ("!! %d DEVICES SHARE THIS IP" % len(g)) if not prefix else ("!! PEER LINK OF %d DEVICES" % len(g))
            row = (hop, ip, label, "", "")
            shown = g if a.all else g[:a.max_dups]
            for h, e in shown:
                det.append("      - %s  |  %s  |  %s" % (h, short_ifs(e["ifs"]), ", ".join(e["srcs"])))
            if len(shown) < len(g):
                det.append("      ... and %d more (use --all to list)" % (len(g) - len(shown)))
        main_rows.append(row)
        details.append(det)

    header = ("hop", "ip", "router", "interface", "source")
    widths = [max(len(str(r[i])) for r in main_rows + [header]) for i in range(5)]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*header))
    for row, det in zip(main_rows, details):
        print(fmt.format(*row).rstrip())
        for d in det:
            print(d)


if __name__ == "__main__":
    main()
