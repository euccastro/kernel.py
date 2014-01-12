# -*- coding: utf-8 -*-

import string
from StringIO import StringIO
import sys


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

def tokens(stream):
    try:
        while True:
            yield token(stream)
    except EOFError:
        pass

# Return the longest token matched by the head of the stream, or None
# if no token can be matched.
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
    first = filename, line, col, c = stream.read_char()
    if c in '()':
        return first + (c,)
    stream.put_back(first)
    ret = string_(stream)
    if ret:
        return ret
    chars = to_delimiter_or_EOF(stream)
    if not chars:
        return None
    s = ''.join(char[-1] for char in chars)
    for name, parser in [('boolean', boolean),
                         ('character', character),
                         ('fixnum', fixnum),
                         ('flonum', flonum),
                         ('.', dot),
                         ('identifier', identifier)]:
        val = parser(s)
        if val is not None:
            return filename, line, col, name, val
    for char in reversed(chars):
        stream.put_back(char)
    return None

def string_(stream):
    first = filename, line, col, c = stream.read_char()
    if c != '"':
        stream.put_back(first)
        return None
    escape = False
    ret = []
    while True:
        next = filename_, line_, col_, c = stream.read_char()
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
                return filename, line, col, 'string', ''.join(ret)
            else:
                ret.append(c)

named_chars = {'#\\alarm': '\a',
               '#\\backspace': '\b',
               '#\\delete': '\x7f',
               '#\\escape': '\x1b',
               '#\\newline': '\n',
               '#\\null': '\x00',
               '#\\return': '\r',
               '#\\space': ' ',
               '#\\tab': '\t'}

def character(s):
    if not s.startswith('#\\'):
        return None
    if len(s) == 3:
        return s[2]
    elif len(s) > 3:
        return named_chars.get(s)
    return None

def fixnum(s):
    try:
        return int(s)
    except ValueError:
        return None

def flonum(s):
    try:
        return float(s)
    except ValueError:
        return None

booleans = {'#t': True, '#f': False}
boolean = booleans.get

def dot(s):
    if s == '.':
        return '.'
    else:
        return None

def identifier(s):
    if s in '+-':
        return s
    if s[0] not in first_identifier_chars:
        return None
    for c in s[1:]:
        if c not in rest_identifier_chars:
            return None
    return s

# Exceptions.

class mismatch(Exception): pass

class kernel_syntax_error(Exception):
    def __init__(self, filename, line, col, msg):
        self.filename = filename
        self.line = line
        self.col = col
        self.msg = msg
    def __str__(self):
        return "SYNTAX ERROR at file %s, line %s, column %s -- %s" % (self.filename,
                                                                      self.line,
                                                                      self.col,
                                                                      self.msg)

# Stream utilities: keep track of line and column numbers, and support
# backtracking.

class stream_adapter:
    def __init__(self, stream, filename):
        self.stream = stream
        self.filename = filename
    def read_char(self):
        ret = self.stream.read(1)
        if not ret:
            raise EOFError
        return self.filename, ret

class line_col_enumerator:
    def __init__(self, stream):
        self.stream = stream
        self.line = 1
        self.column = 0
    def read_char(self):
        filename, c = self.stream.read_char()
        if c == '\n':
            # The line and columns of whitespace will never be used, so we only
            # care that subsequent characters will get correct ones.
            self.line += 1
            self.column = 0
        else:
            self.column += 1
        return filename, self.line, self.column, c

class bufferer:
    def __init__(self, stream):
        self.stream = stream
        self.backlog = []
    def read_char(self):
        if self.backlog:
            return self.backlog.pop()
        else:
            return self.stream.read_char()
    def put_back(self, s):
        self.backlog.append(s)


# Other utilities.

def match(stream, string):
    backlog = []
    for c in string:
        try:
            backlog.append(stream.read_char())
            if backlog[-1][-1] != c:
                raise mismatch
        except (EOFError, mismatch):
            for each in reversed(backlog):
                stream.put_back(each)
            return False
    return True

def to_delimiter_or_EOF(stream):
    ret = []
    try:
        while True:
            next = _, _, _, c = stream.read_char()
            if c in delimiters:
                stream.push_back(c)
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
        check_token(('basic %r' % basic), basic, basic, basic)
        check_token(('basic %r with something after' % basic),
                    basic + 'etc',
                    basic,
                    basic)
    #XXX: add more string niceties defined in R7RS?
    for src, body in [('"basic string"', "basic string"),
                      (r'"escaped\nnewline"', "escaped\nnewline"),
                      ('"physical\nnewline"', "physical\nnewline"),
                      (r'"escaped\"doublequote"', "escaped\"doublequote"),
                      ('"literal double quo"te"', "literal double quo")]:
        check_token(('string %r' % src), src, 'string', body)
    #XXX: hex escapes?
    for src, char in [(r'#\a', 'a'),
                      (r'#\newline', '\n')]:
        check_token(('char %r' % src), src, 'character', char)
    for src, type, in [('1', 'fixnum'),
                       ('1.2', 'flonum'),
                       ('.1', 'flonum'),
                       ('+1', 'fixnum'),
                       ('-1', 'fixnum'),
                       ('+.1', 'flonum'),
                       ('+1.2', 'flonum'),
                       ('-1.2', 'flonum')]:
        check_token("number %r" % src, src, type, eval(src))
    for src, b in [('#t', True),
                   ('#f', False)]:
        check_token("boolean %r" % src, src, 'boolean', b)
    check_token('.', '.', '.', '.')
    for src in ['$lambda',
                'list->vector',
                '+',
                '<=?',
                'the-word-recursion-has-many-meanings',
                'q',
                'soup',
                'V17a',
                'a34kTMNs']:
        check_token('identifier %r' % src, src, 'identifier', src)
    check_not_token('. with something after', '.blah')
    check_not_token("start looks like a number", '123abc')
    check_not_token("start looks like a boolean", '#false')
    check_not_token("start looks like a character", '#\\unrecognized')


# Utilities used by tests only.

def sfs(s):
    "Stream from string."
    return bufferer(line_col_enumerator(stream_adapter(StringIO(s), '<stdin>')))

def check_token(title, s, tok_type, tok_body):
    if token(sfs(s)) != ('<stdin>', 1, 1, tok_type, tok_body):
        print >> sys.stderr
        print >> sys.stderr, "*** test %s FAILED:" % title
        print >> sys.stderr, "Expected:", ('<stdin>', 1, 1, tok_type, tok_body)
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
