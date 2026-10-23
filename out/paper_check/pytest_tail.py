import pathlib
p = pathlib.Path("out/paper_check/pytest.log")
b = p.read_bytes()
print("bytes", len(b))
print(repr(b[-600:]))
