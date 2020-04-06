def __getattribute__(self, name):
    if name in {{ method.removeAttrs }} and name not in _f.EXCLUDE_METHODS:  # tmp fix
        raise AttributeError("'{{ classname }}' object has no attribute '" + name + "'")
    return super().__getattribute__(name)