from characters import name_from_char

class kernel_type(object):
    def __init__(self, val):
        self.check(val)
        self.val = val
    def check(self, val):
        pass
    def __repr__(self):
        return repr(self.val)
    def __eq__(self, other):
        return isinstance(other, self.__class__) and other.val == self.val
    def __ne__(self, other):
        return not self.__eq__(other)

class nil(kernel_type):
    def __init__(self):
        pass
    def __eq__(self, other):
        return other is self
    def __repr__(self):
        return "()"
nil = nil()

class boolean(kernel_type):
    def check(self, val):
        assert isinstance(val, bool)
    def __repr__(self):
        if self.val:
            return "#t"
        else:
            return "#f"
true = boolean(True)
false = boolean(False)

class string(kernel_type):
    def check(self, val):
        assert isinstance(val, str)

class symbol(string):

    table = {}

    def __repr__(self):
        return "'%s" % self.val

    @classmethod
    def intern(cls, s):
        ret = cls.table.get(s)
        if ret is None:
            ret = symbol(s)
            cls.table[s] = ret
        return ret

    def __eq__(self, other):
        return other is self

class character(kernel_type):
    def check(self, val):
        assert isinstance(val, str) and len(val) == 1
    def __repr__(self):
        # XXX: hex codes!
        return name_from_char.get(self.val, "#\%s" % self.val)

class fixnum(kernel_type):
    def check(self, val):
        assert isinstance(val, int)

class flonum(kernel_type):
    def check(self, val):
        assert isinstance(val, float)

class pair(kernel_type):
    def __init__(self, car, cdr):
        self.car = car
        self.cdr = cdr
    def __repr__(self):
        ret = ["(%r" % self.car]
        cdr = self.cdr
        while isinstance(cdr, pair):
            ret.append(" %r" % cdr.car)
            cdr = cdr.cdr
        if cdr is nil:
            ret.append(")")
        else:
            ret.append(" . %r)" % cdr)
        return "".join(ret)
    def __eq__(self, other):
        return (isinstance(other, pair)
                and other.car == self.car
                and other.cdr == self.cdr)
