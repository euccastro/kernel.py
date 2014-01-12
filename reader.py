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
    tok = filename, line, col, type, val = ts.next()
    if type == '(':
        pre_dot = []
        try:
            while True:
                filename_, line_, col_, type, val = ts.next()
                if type == '.':
                    if not pre_dot:
                        raise kernel_syntax_error(filename_, line_, col_,
                                                  "malformed improper list (no data before dot)")
                    post_dot = datum_from_token_stream(ti)
                    filename_, line_, col_, type, val = ts.next()
                    if type != ')':
                        raise kernel_syntax_error(filename_, line_, col_,
                                                  "closing ) expected at end of improper list")
                    return filename, line, col, 'pair', cons_star(pre_dot, post_dot)
                elif type == ')':
                    return filename, line, col, 'list', cons_star(pre_dot, nil)
                else:
                    ts.push_back(next)
                    pre_dot.append(datum_from_token_stream(ts))
        except EOFError:
            raise kernel_syntax_error(filename, line, col,
                                      "incomplete form")
    else:
        return s


def tokens(stream):
    try:
        while True:
            yield token(stream)
    except EOFError:
        pass

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
    first = stream.next()
    if first.data in '()':
        return first
    stream.put_back(first)
    ret = string_(stream)
    if ret:
        return ret
    chars = to_delimiter_or_EOF(stream)
    if not chars:
        return None
    s = ''.join(char.data for char in chars)
    for parser in [boolean, character, fixnum, flonum, dot, identifier]:
        val = parser(s)
        if val is not None:
            return syntax(first.filename, first.line, first.col, val)
    stream.put_back_iter(chars)
    return None

def string_(stream):
    first = stream.next()
    if first.data != '"':
        stream.put_back(first)
        return None
    escape = False
    ret = []
    try:
        while True:
            c = stream.next().data
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
                    return syntax(first.filename, first.line, first.col,
                                  ktype.string(''.join(ret)))
                else:
                    ret.append(c)
    except EOFError:
        raise kernel_syntax_error(first, "unclosed string literal")


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
    def __init__(self, syntax, msg):
        self.syntax = syntax
        self.msg = msg
    def __str__(self):
        return ("SYNTAX ERROR at file %s, line %s, column %s -- %s"
                % (self.syntax.filename,
                   self.syntax.line,
                   self.syntax.col,
                   self.msg))


# Stream utilities: keep track of filename, line and column numbers, and support
# backtracking.

class syntax:
    "Anything that has associated a filename, line, and column in source code."
    def __init__(self, filename, line, col, data):
        self.filename = filename
        self.line = line
        self.col = col
        self.data = data
    def __repr__(self):
        return ("syntax(filename=%r, line=%r, col=%r, data=%r)"
                % (self.filename, self.line, self.col, self.data))
    def __eq__(self, other):
        "For testing."
        return (isinstance(other, syntax)
                and other.filename == self.filename
                and other.line == self.line
                and other.col == self.col
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
            raise EOFError
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
        return syntax(filename, self.line, self.column, c)

class bufferer:
    """
    A stream that supports pushing read values back.

    Take a stream.
    """
    def __init__(self, stream):
        self.stream = stream
        self.backlog = []
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
            if backlog[-1].data != c:
                raise mismatch
        except (EOFError, mismatch):
            stream.put_back_iter(backlog)
            return False
    return True

def to_delimiter_or_EOF(stream):
    ret = []
    try:
        while True:
            next = stream.next()
            if next.data in delimiters:
                stream.push_back(next)
                break
            else:
                ret.append(next)
    except EOFError:
        pass
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
                    basic)
    #XXX: add more string niceties defined in R7RS?
    for src, body in [('"basic string"', "basic string"),
                      (r'"escaped\nnewline"', "escaped\nnewline"),
                      ('"physical\nnewline"', "physical\nnewline"),
                      (r'"escaped\"doublequote"', "escaped\"doublequote"),
                      ('"literal double quo"te"', "literal double quo")]:
        check_token(('string %r' % src), src, ktype.string(body))
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


# Utilities used by tests only.

def sfs(s):
    "Stream from string."
    return bufferer(line_col_enumerator(stream_adapter(StringIO(s), '<stdin>')))

def check_token(title, s, tok):
    if token(sfs(s)) != syntax('<stdin>', 1, 1, tok):
        print >> sys.stderr
        print >> sys.stderr, "*** test %s FAILED:" % title
        print >> sys.stderr, "Expected:", syntax('<stdin>', 1, 1, tok)
        print >> sys.stderr, "But got :", token(sfs(s))
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
    print
    print "All OK!"
