import math
N = 1000000
c = 0
for x in range(2, N + 1):
    p = True
    r = int(math.isqrt(x))
    for d in range(2, r + 1):
        if x % d == 0:
            p = False
            break
    if p:
        c += 1
print(c)
