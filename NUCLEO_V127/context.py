"""Small observable context, computed from initial observations only."""
KEYS=tuple(f"{shape}:{diversity}" for shape in ("monotone","nonmonotone") for diversity in ("low","high"))
def context(fit):
    if not fit or len(dict(fit))!=len(fit):raise ValueError("fit")
    ys=[y for x,y in sorted(fit)]
    ds=[b-a for a,b in zip(ys,ys[1:])]
    mono=all(d>=0 for d in ds) or all(d<=0 for d in ds)
    return ("monotone" if mono else "nonmonotone")+":"+("low" if len(set(ys))<=3 else "high")
