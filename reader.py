# -*- coding: utf-8 -*-

import string
from StringIO import StringIO
import sys

from characters import char_from_name
import kernel_type as ktype


# Deviations from Kernel:
#
#  - We accept λ (for $lambda).  While $vau is more fundamental in kernel,
#    I expect we'll use it less often.
#
#  - Identifiers are case sensitive.  Case insensitivity would make force
#    us to take extra steps to disambiguate identifiers when doing
#    straightforward ffi wrappers.
#

first_identifier_chars = string.letters + "!$%&*/:<=>?@^_~λ"
rest_identifier_chars = first_identifier_chars + string.digits + "+-."

invalid = "`',"
delimiters = string.whitespace + '();"'


def datum_from_token_stream(ts):
    first = ts.next()
    if first.data == '(':
        pre_dot = []
        for next in ts:
            if next.data == '.':
                if not pre_dot:
                    raise kernel_syntax_error(
                            next.start,
                            "malformed improper list (no data before dot)")
                post_dot = datum_from_token_stream(ts)
                next = ts.next()
                if next.data != ')':
                    raise kernel_syntax_error(
                            next.start,
                            "closing ) expected at end of improper list")
                return syntax(first.start,
                              next.end,
                              cons_star(pre_dot, post_dot))
            elif next.data == ')':
                return syntax(first.start,
                              next.end,
                              cons_star(pre_dot, ktype.nil))
            else:
                ts.put_back(next)
                pre_dot.append(datum_from_token_stream(ts))
        else:
            raise kernel_syntax_error(first.start,
                                      "incomplete form")
    else:
        assert isinstance(first.data, ktype.kernel_type), repr(first.data)
        return first

def cons_star(pre_dot, post_dot):
    ret = post_dot
    for car in reversed(pre_dot):
        ret = ktype.pair(car, ret)
    return ret

def tokens(stream):
    while True:
        yield token(stream)

# Return the longest token matched by the head of the stream, or None if no
# token can be matched.
#
# From R7RS, page 62
#
# (but note
#     #( #u8( ' ` , ,@
#  are not tokens in Kernel.)
#
# token = <identifier> | <boolean> | <number> | <character>  | <string>
#       | ( | ) | .
def token(stream):
    skip_whitespace(stream)
    startpos, c = stream.next()
    if c in '()':
        return syntax(startpos, startpos.next(), c)
    stream.put_back((startpos, c))
    ret = string_(stream)
    if ret:
        return ret
    chars = to_delimiter_or_end(stream)
    if not chars:
        return None
    s = ''.join(c for pos, c in chars)
    for parser in [boolean, character, fixnum, flonum, dot, identifier]:
        val = parser(s)
        if val is not None:
            endpos = chars[-1][0].next()
            return syntax(startpos, endpos, val)
    stream.put_back_iter(chars)
    return None

def skip_whitespace(stream):
    for next, c in stream:
        if c == ';':
            skip_to_end_of_line(stream)
        elif c not in string.whitespace:
            stream.put_back((next, c))
            break

def skip_to_end_of_line(stream):
    for next, c in stream:
        if c == '\n':
            break

def string_(stream):
    startpos, c = stream.next()
    if c != '"':
        stream.put_back((startpos, c))
        return None
    escape = False
    ret = []
    for nextpos, c in stream:
        if escape:
            if c == "n":
                ret.append('\n')
            else:
                ret.append(c)
            escape = False
        else:
            if c == "\\":
                escape = True
            elif c == '"':
                return syntax(startpos, nextpos.next(),
                              ktype.string(''.join(ret)))
            else:
                ret.append(c)
    else:
        raise kernel_syntax_error(startpos, "unclosed string literal")

def character(s):
    if not s.startswith('#\\'):
        return None
    if len(s) == 3:
        return ktype.character(s[2])
    elif s in char_from_name:
        return ktype.character(char_from_name[s])
    return None

def fixnum(s):
    try:
        return ktype.fixnum(int(s))
    except ValueError:
        return None

def flonum(s):
    try:
        return ktype.flonum(float(s))
    except ValueError:
        return None

booleans = {'#t': True, '#f': False}
def boolean(s):
    if s in booleans:
        return ktype.boolean(booleans[s])
    else:
        return None

def dot(s):
    if s == '.':
        return '.'
    else:
        return None

def identifier(s):
    # In kernel all identifiers are names for symbols.
    if s in '+-':
        return ktype.symbol.intern(s)
    if s[0] not in first_identifier_chars:
        return None
    for c in s[1:]:
        if c not in rest_identifier_chars:
            return None
    return ktype.symbol.intern(s)

# Exceptions.

class mismatch(Exception): pass

class kernel_syntax_error(Exception):
    def __init__(self, pos, msg):
        self.pos = pos
        self.msg = msg
    def __str__(self):
        return ("SYNTAX ERROR at file %s, line %s, column %s -- %s"
                % (self.pos.filename,
                   self.pos.line,
                   self.pos.col,
                   self.msg))


# Stream utilities: keep track of filename, line and column numbers, and
# support backtracking.

class position:
    def __init__(self, filename, line, col):
        self.filename = filename
        self.line = line
        self.col = col
    def __eq__(self, other):
        return (isinstance(other, position)
                and other.filename == self.filename
                and other.line == self.line
                and other.col == self.col)
    def __ne__(self, other):
        return not self.__eq__(other)
    def __str__(self):
        return "%s(%s,%s)" % (self.filename, self.line, self.col)
    def __repr__(self):
        return ("position(filename=%r, line=%s, col=%s)"
                % self.filename, self.line, self.col)
    def next(self):
        return position(self.filename, self.line, self.col + 1)

class syntax:
    "Anything that has associated a start and end location in source code."
    def __init__(self, start, end, data):
        self.start = start
        self.end = end
        self.data = data
    def __repr__(self):
        return ("syntax(start=%s, end=%s, data=%r)"
                % (self.start, self.end, self.data))
    def __eq__(self, other):
        "For testing."
        return (isinstance(other, syntax)
                and other.start == self.start
                and other.end == self.end
                and other.data == self.data)
    def __ne__(self, other):
        return not self.__eq__(other)

class stream_adapter:
    """
    A stream of (filename, char) pairs.

    Take an object supporting the file protocol and a file name.
    """
    def __init__(self, stream, filename):
        self.stream = stream
        self.filename = filename
    def read_char(self):
        ret = self.stream.read(1)
        if not ret:
            raise StopIteration
        return self.filename, ret

class line_col_enumerator:
    """
    A stream of syntax objects with a single character each.

    Take a stream_adapter.
    """
    def __init__(self, stream):
        self.stream = stream
        self.line = 1
        self.column = 0
    def next(self):
        filename, c = self.stream.read_char()
        if c == '\n':
            # The line and columns of whitespace will never be used, so we only
            # care that subsequent characters will get correct ones.
            self.line += 1
            self.column = 0
        else:
            self.column += 1
        return position(filename, self.line, self.column), c

class bufferer:
    """
    A stream that supports pushing read values back.

    Take a stream.
    """
    def __init__(self, stream):
        self.stream = stream
        self.backlog = []
    def __iter__(self):
        return self
    def next(self):
        if self.backlog:
            return self.backlog.pop()
        else:
            return self.stream.next()
    def put_back(self, s):
        self.backlog.append(s)
    def put_back_iter(self, iter):
        for each in reversed(iter):
            self.put_back(each)


# Other utilities.

def match(stream, string):
    backlog = []
    for c in string:
        try:
            backlog.append(stream.next())
            if backlog[-1][1] != c:
                raise mismatch
        except (StopIteration, mismatch):
            stream.put_back_iter(backlog)
            return False
    return True

def to_delimiter_or_end(stream):
    ret = []
    for nextpos, c in stream:
        if c in delimiters:
            stream.put_back((nextpos, c))
            break
        else:
            ret.append((nextpos, c))
    return ret

# Tests.

def test_token():
    for not_token in ",'` \t\n":  # invalid plus whitespace
        check_not_token(('invalid %r' % invalid), invalid)
        check_not_token(('invalid %r with something after' % invalid), invalid + 'etc')
    for basic in '()':
        check_token(('basic %r' % basic), basic, basic)
        check_token(('basic %r with something after' % basic),
                    basic + 'etc',
                    basic,
                    1, 1,
                    1, 2)
    #XXX: add more string niceties defined in R7RS?
    for src, body, endline, endcol in [
            ('"basic string"', "basic string", 1, None),
            (r'"escaped\nnewline"', "escaped\nnewline", 1, None),
            ('"physical\nnewline"', "physical\nnewline", 2, 9),
            (r'"escaped\"doublequote"', "escaped\"doublequote", 1, None),
            ('"literal double quo"te"', "literal double quo", 1, 21)]:
        check_token(('string %r' % src),
                    src,
                    ktype.string(body),
                    1, 1,
                    endline, endcol)
    #XXX: hex escapes?
    for src, char in [(r'#\a', 'a'),
                      (r'#\newline', '\n')]:
        check_token(('char %r' % src), src, ktype.character(char))
    for src, type, in [('1', 'fixnum'),
                       ('1.2', 'flonum'),
                       ('.1', 'flonum'),
                       ('+1', 'fixnum'),
                       ('-1', 'fixnum'),
                       ('+.1', 'flonum'),
                       ('+1.2', 'flonum'),
                       ('-1.2', 'flonum')]:
        check_token("number %r" % src, src, getattr(ktype, type)(eval(src)))
    for src, b in [('#t', True),
                   ('#f', False)]:
        check_token("boolean %r" % src, src, ktype.boolean(b))
    check_token('.', '.', '.')
    for src in ['$lambda',
                'list->vector',
                '+',
                '<=?',
                'the-word-recursion-has-many-meanings',
                'q',
                'soup',
                'V17a',
                'a34kTMNs']:
        check_token('identifier %r' % src, src, ktype.symbol.intern(src))
    check_not_token('. with something after', '.blah')
    check_not_token("start looks like a number", '123abc')
    check_not_token("start looks like a boolean", '#false')
    check_not_token("start looks like a character", '#\\unrecognized')
    check_token("ignore leading whitespace",
                "    blah",
                ktype.symbol.intern('blah'),
                1, 5, 1, 9)
    check_token("ignore comments",
                "   ; This is a comment\n    blah",
                ktype.symbol.intern('blah'),
                2, 5, 2, 9)
    #XXX: R7RS #; datum comments.

def test_datum():
    start = pos(1, 1)
    check_equal("Atomic datum",
                dfs("#t"),
                syntax(start,
                       pos(1, 3),
                       ktype.true))
    check_equal("Simple proper list datum",
                dfs("(#t #f)"),
                syntax(start,
                       pos(1, 8),
                       ktype.pair(syntax(pos(1, 2),
                                         pos(1, 4),
                                         ktype.true),
                                  ktype.pair(syntax(pos(1, 5),
                                                    pos(1, 7),
                                                    ktype.false),
                                             ktype.nil))))
    check_equal("Simple pair datum",
                dfs("(a . 5)"),
                syntax(start,
                       pos(1, 8),
                       ktype.pair(syntax(pos(1, 2),
                                         pos(1, 3),
                                         ktype.symbol.intern('a')),
                                  syntax(pos(1, 6),
                                         pos(1, 7),
                                         ktype.fixnum(5)))))

# Utilities used by tests only.

def sfs(s):
    "Stream from string."
    return bufferer(line_col_enumerator(stream_adapter(StringIO(s), '<stdin>')))

def dfs(s):
    "Datum from string."
    return datum_from_token_stream(bufferer(tokens(sfs(s))))

def pos(line, col):
    return position('<stdin>', line, col)

def check_token(title, s, tok,
                startline=1, startcol=1,
                endline=1, endcol=None):
    if endcol is None:
        endcol = 1+len(s)
    expected = syntax(position('<stdin>', startline, startcol),
                      position('<stdin>', endline, endcol),
                      tok)
    actual = token(sfs(s))
    check_equal(title, actual, expected)

def check_equal(title, actual, expected):
    if actual != expected:
        print >> sys.stderr
        print >> sys.stderr, "*** test %s FAILED:" % title
        print >> sys.stderr, "Expected:", expected
        print >> sys.stderr, "But got :", actual
        print >> sys.stderr
        assert False

def check_not_token(title, s):
    if token(sfs(s)) is not None:
        print >> sys.stderr
        print >> sys.stderr, "*** test (not a token) %r FAILED:" % title
        print >> sys.stderr, ("Expected %s not to be a token, but it's identified as a %r"
                              % (s, token(sfs(s))))
        print >> sys.stderr
        assert False


if __name__ == '__main__':
    test_token()
    test_datum()
    print
    print "All OK!"
