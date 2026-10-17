def to_lines(items):
    """items: list of (x0, y0, x1, y1, text) -> text in reading order (top-down, left-right)."""
    items = sorted(items, key=lambda t: (t[1] + t[3]) / 2)
    lines = []
    for it in items:
        cy, h = (it[1] + it[3]) / 2, it[3] - it[1]
        if lines and abs(cy - lines[-1][0]) < h * 0.5:
            lines[-1][1].append(it)
        else:
            lines.append([cy, [it]])
    return '\n'.join(' '.join(t[4] for t in sorted(l[1], key=lambda t: t[0])) for l in lines)
