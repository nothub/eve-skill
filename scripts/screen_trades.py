#!/usr/bin/env python3
"""Screen station-trading candidates in one region, validated against traded history.

The order book alone is not evidence: a single inflated sell order costs almost nothing
to place and makes a dead item look hugely profitable. Every candidate here has its sell
side priced from what actually traded, not from what someone is asking.

Needs the SDE for type names: EVE_SDE_DB, or the XDG default.
"""
import argparse, json, os, sqlite3, statistics, sys, urllib.request

ESI = "https://esi.evetech.net"
FUZZ = "https://market.fuzzwork.co.uk/aggregates/"


def headers():
    ua = os.environ.get("EVE_ESI_UA", "eve-notes/1.0")
    contact = os.environ.get("EVE_ESI_CONTACT")
    return {"User-Agent": f"{ua} ({contact})" if contact else ua,
            "X-Compatibility-Date": os.environ.get("EVE_ESI_COMPAT", "2026-08-18")}


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=headers())))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--region", type=int, default=10000002, help="default 10000002 (The Forge / Jita)")
    p.add_argument("--capital", type=float, default=0, help="ISK available; 0 for no cap")
    p.add_argument("--slots", type=int, default=17, help="order slots; each item uses two")
    p.add_argument("--tax", type=float, default=0.075, help="sales tax; alpha 0.075, omega w/ Accounting V ~0.0375")
    p.add_argument("--broker", type=float, default=0.024, help="broker fee per side")
    p.add_argument("--min-price", type=float, default=20_000)
    p.add_argument("--max-price", type=float, default=8_000_000)
    p.add_argument("--min-volume", type=int, default=150, help="median daily units traded")
    p.add_argument("--min-orders", type=int, default=30, help="median distinct daily orders")
    p.add_argument("--capture", type=float, default=0.10, help="share of daily volume assumed winnable")
    p.add_argument("--probe", type=int, default=160, help="how many wide spreads to check history for")
    a = p.parse_args()

    sde = os.environ.get("EVE_SDE_DB") or os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "eve-sde", "sde.db")
    if not os.path.exists(sde):
        sys.exit(f"SDE not found at {sde}. See the skill's SDE section for the download command.")
    db = sqlite3.connect(sde)
    names = dict(db.execute("select typeID, typeName from invTypes"))
    ids = [r[0] for r in db.execute(
        "select t.typeID from invTypes t join invGroups g on g.groupID = t.groupID "
        "where t.published = 1 and t.marketGroupID is not null "
        "and g.categoryID in (4,6,7,8,17,18,20,22,32,43)")]

    px = {}
    for i in range(0, len(ids), 400):
        chunk = ",".join(map(str, ids[i:i + 400]))
        px.update(get(f"{FUZZ}?region={a.region}&types={chunk}"))

    # Cheap pre-filter on the book, then spend history requests only on plausible ones.
    pre = []
    for t, v in px.items():
        bid, ask = float(v["buy"]["max"]), float(v["sell"]["min"])
        if not (a.min_price <= bid <= a.max_price) or ask <= bid:
            continue
        # Both sides need depth. A thin ask side is how an item ends up with a wide
        # spread nobody ever paid, and it is far cheaper to reject here than to spend
        # a history request discovering it.
        if float(v["buy"]["volume"]) < 5000 or float(v["sell"]["volume"]) < 5000:
            continue
        pre.append(((ask - bid) / bid, int(t), bid, ask))
    # Widest-spread-first is exactly what manipulation looks like, so this ordering spends
    # the probe budget on the likeliest fakes. Kept because it also finds the real outliers,
    # but raise --probe rather than trusting a shallow run.
    pre.sort(reverse=True)

    out = []
    for _, t, bid_now, ask_now in pre[:a.probe]:
        try:
            hist = get(f"{ESI}/markets/{a.region}/history?type_id={t}")[-90:]
        except Exception:
            continue
        if len(hist) < 60:
            continue
        vol = statistics.median(d["volume"] for d in hist)
        orders = statistics.median(d["order_count"] for d in hist)
        if vol < a.min_volume or orders < a.min_orders:
            continue
        avg = statistics.median(d["average"] for d in hist)
        bid = bid_now + 0.01
        ask = min(ask_now - 0.01, avg)                 # never assume a sale above what trades
        if bid > avg * 0.95:                           # must buy meaningfully below the traded average
            continue
        if sum(1 for d in hist if ask > d["highest"]) > len(hist) * 0.25:
            continue                                   # ask has to clear on most days
        net = ask * (1 - a.tax - a.broker) - bid * (1 + a.broker)
        if net <= 0:
            continue
        out.append({"name": names[t], "type_id": t, "bid": bid, "ask": ask, "avg": avg,
                    "net": net, "qty": max(1, int(vol * a.capture)), "vol": vol, "orders": orders})

    out.sort(key=lambda r: -r["net"] * r["qty"])
    print(f"{'item':<36}{'buy @':>12}{'sell @':>12}{'90d avg':>11}{'qty':>7}{'ISK in':>13}{'profit':>12}")
    spent = profit = 0
    slots_left = a.slots
    for r in out:
        if slots_left < 2:                             # each item needs a buy and a sell order
            break
        cap = r["bid"] * r["qty"]
        if a.capital and spent + cap > a.capital:      # skip what no longer fits, keep looking
            continue
        print(f"{r['name'][:35]:<36}{r['bid']:>12,.2f}{r['ask']:>12,.2f}{r['avg']:>11,.0f}"
              f"{r['qty']:>7,}{cap:>13,.0f}{r['net'] * r['qty']:>12,.0f}")
        spent += cap
        profit += r["net"] * r["qty"]
        slots_left -= 2
    print(f"{'':<36}{'':>12}{'':>12}{'':>11}{'':>7}{spent:>13,.0f}{profit:>12,.0f}")
    print(f"\n{len(out)} of {min(a.probe, len(pre))} screened survived history validation.")
    print("Prices move fast. Re-run before acting on an old list.")


if __name__ == "__main__":
    main()
