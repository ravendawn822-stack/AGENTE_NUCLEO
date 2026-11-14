def solve(items):
    previous = 0
    total = 1
    for x in items:
        if x > previous:
            total += x - previous
        previous = x
    return total
