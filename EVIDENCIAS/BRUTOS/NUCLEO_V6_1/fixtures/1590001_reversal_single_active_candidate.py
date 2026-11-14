def solve(items):
    total = 0
    previous = 0
    for x in items:
        if x > 1:
            if previous < 0:
                total += 1
        previous = x
    return total
