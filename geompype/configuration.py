"""Read hierarchical YAML with includes, inherited values and explicit variants.

Referenced YAML files are resolved against the main YAML file's directory.
Component dictionaries inherit missing values from their parent. ``name__0``
entries override independent copies of ``name``; dotted override keys are
supported. Explicit length/angle strings become live named Parameters. Counts,
flags and names remain ordinary Python values; non-geometric units remain
metadata strings. The loader never evaluates Python expressions or writes files.
"""

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
import re

from .parameters import Parameter

_QUANTITY = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(nm|um|µm|μm|mm|m|deg|rad)\s*$")


def _merge(base, override):
    result = deepcopy(base)
    for key, value in override.items():
        parts = key.split(".")
        target = result
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            if not isinstance(target[part], dict):
                raise ValueError(f"Override {key!r} traverses a scalar value.")
            target = target[part]
        leaf = parts[-1]
        if isinstance(value, dict) and isinstance(target.get(leaf), dict):
            target[leaf] = _merge(target[leaf], value)
        else:
            target[leaf] = deepcopy(value)
    return result


def _identifier(name):
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(name))
    return name if name and name[0].isalpha() else "cfg_"+name


class ConfigNode(Mapping):
    """A configuration scope with lazy Parameters and nearest-parent lookup.

    Access a child with ``node.child('device')`` and a value with
    ``node['width']``. Inherited values share the parent's Parameter.
    ``raw(key)`` returns a copy of the original data. ``variations('element')``
    returns independent scopes in numeric suffix order, or the base as a single
    element when no indexed variation exists.
    """

    def __init__(self, data, *, name="config", parent=None, source=None):
        if not isinstance(data, dict) or any(not isinstance(k,str) for k in data):
            raise ValueError("A configuration scope requires a mapping with string keys.")
        self._data = deepcopy(data)
        self.name, self.parent, self.source = _identifier(name), parent, source
        self._cache = {}

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        if key not in self._data:
            if self.parent is not None:
                return self.parent[key]
            raise KeyError(f"Missing configuration value {key!r} in {self.name}.")
        if key not in self._cache:
            self._cache[key] = self._convert(self._data[key], key, literal=key.endswith("__n"))
        return self._cache[key]

    def _convert(self, value, key, literal=False):
        name = self.name+"_"+_identifier(key)
        if isinstance(value, dict):
            return ConfigNode(value, name=name, parent=self, source=self.source)
        if isinstance(value, list):
            return [self._convert(v,f"{key}_{i}",literal) for i,v in enumerate(value)]
        if isinstance(value,str) and not literal:
            match = _QUANTITY.fullmatch(value)
            if match:
                return Parameter(float(match[1]),name,unit=match[2],
                                 description=f"{self.source or 'YAML'}: {key}")
        return value

    def raw(self, key):
        """Copy the original local or inherited value, without Parameter conversion.

        Parameter edits do not change this source-data snapshot.
        """
        if key in self._data:
            return deepcopy(self._data[key])
        if self.parent is not None:
            return self.parent.raw(key)
        raise KeyError(key)

    def child(self, name):
        """Return a nested ConfigNode; missing values inherit from its parent.

        Raise TypeError if the requested value is not a mapping.
        """
        result = self[name]
        if not isinstance(result, ConfigNode):
            raise TypeError(f"{name!r} is not a component mapping.")
        return result

    def variations(self, name):
        """Return cached scopes for local ``name__N`` overrides, in numeric order.

        Each variant owns a copy of the base mapping. If there are no variants,
        return a one-element tuple containing the base child. Inherited values
        still refer to the parent scope's Parameters.
        """
        cache_key = ("variations",name)
        if cache_key not in self._cache:
            base = self.raw(name)
            if not isinstance(base,dict):
                raise TypeError("Variation base must be a component mapping.")
            pattern = re.compile(re.escape(name)+r"__(\d+)$")
            indices = sorted((int(m[1]),key) for key in self._data if (m := pattern.fullmatch(key)))
            if not indices:
                result = (self.child(name),)
            else:
                result = tuple(ConfigNode(_merge(base,self._data[key] or {}),
                                          name=self.name+"_"+key,parent=self,source=self.source)
                               for _,key in indices)
            self._cache[cache_key] = result
        return self._cache[cache_key]


def load_config(path, *, name=None, overrides=None):
    """Load a YAML mapping as a ConfigNode, without executing Python code.

    ``path`` names the main file. Every string ending in .yaml/.yml is an
    include relative to that file's directory, including nested references.
    Included files may contain mappings or coordinate lists; cycles are refused.
    ``name`` prefixes generated Parameter names and defaults to the file stem.
    ``overrides`` merges a mapping, with dotted keys supported, into an in-memory
    copy. The source files are never changed.
    """
    import yaml
    path = Path(path).resolve()
    root = path.parent

    def read(file, stack):
        file = file.resolve()
        if file in stack:
            raise ValueError("Cyclic YAML references: "+" -> ".join(p.name for p in (*stack,file)))
        with file.open(encoding="utf-8-sig") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data,(dict,list)):
            raise ValueError(f"Configuration file {file} must contain a mapping or coordinate list.")
        return expand(data,(*stack,file))

    def expand(value,stack):
        if isinstance(value,dict):
            return {key: expand(v,stack) for key,v in value.items()}
        if isinstance(value,list):
            return [expand(v,stack) for v in value]
        if isinstance(value,str) and value.lower().endswith((".yaml",".yml")):
            return read(root/value,stack)
        return value

    data = read(path,())
    if overrides:
        data = _merge(data,expand(overrides,()))
    return ConfigNode(data,name=name or path.stem,source=str(path))
