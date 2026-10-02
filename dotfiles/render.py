"""Templates of the files features write: system/<path from />.j2, rendered with Jinja2."""

import traceback
from pathlib import Path

import jinja2

from dotfiles.errors import ConfigError
from dotfiles.layout import Layout

_SUFFIX = ".j2"


class _TemplateFail(Exception):
    """Raised by fail() in a template: the data is wrong for this host."""


def _fail(message: str):
    """fail(message) in a template: stop rendering with MESSAGE."""
    raise _TemplateFail(message)


def _environment(directory: Path) -> jinja2.Environment:
    """Jinja2 for the templates under DIRECTORY: strict, no autoescape, tags on their own lines."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(directory),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    env.globals["fail"] = _fail
    return env


def template(dst: str, root: Path = Layout.root, **context) -> str:
    """system/DST.j2 rendered with CONTEXT: the content a feature writes to DST."""
    name = dst.lstrip("/") + _SUFFIX
    try:
        return _environment(Layout(root).system).get_template(name).render(context)
    except (jinja2.TemplateError, _TemplateFail) as e:
        raise _error(e, f"system/{name}") from None


def _error(e: Exception, name: str) -> ConfigError:
    """NAME and the template's line, for any error raised while rendering it."""
    line = getattr(e, "lineno", None)
    for frame in traceback.extract_tb(e.__traceback__):
        if frame.filename.endswith(name):
            line = frame.lineno
    where = name + (f":{line}" if line else "")
    return ConfigError(f"{where}: {getattr(e, 'message', None) or e}")
