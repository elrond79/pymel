def __getattribute__(self, name):
    if name in {{ method.removeAttrs }} and name not in _f.EXCLUDE_METHODS:  # tmp fix
        raise AttributeError("'{{ classname }}' object has no attribute '" + name + "'")
    # we use old-style super because the newsuper implementation in
    # python-2.7 future module will call __getattribute__...
    return super({{ classname }}, self).__getattribute__(name)