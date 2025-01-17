import jinja2


class TraceUndefined(jinja2.Undefined):
    def __getattr__(self, name):
        return TraceUndefined(name=f"{self._undefined_name}.{name}")

    def __getitem__(self, name: str):
        return TraceUndefined(
            name=f"{self._undefined_name}['{name.replace("'", r"\'")}']"
        )

    def __str__(self):
        return f"{{{{ {self._undefined_name} }}}}"


def test_traceundefined():
    src = "{{ foo }} {{ bar.baz }} {{ a.b['c'] }}"
    txt = jinja2.Template(src, undefined=TraceUndefined).render()
    assert src == txt
