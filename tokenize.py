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

identifier_chars = string.letters + string.digits + "!$%&*+-./:<=>?@^_~λ"
invalid = "`',"

# XXX: Only the most straightforward fixnums and flonums supported yet.  No
# ratios, complex numbers, nor exponent notation.
first_number_char = string.digits + "+-."
rest_number_char = string.digits + "."

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
    # The `identifier` production also recognizes the dot ('.') token.
    for production in string_, character, number, boolean, identifier:
        ret = production(stream)
        if ret:
            return ret
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

def character(stream):
    first = filename, line, col, _ = stream.read_char()
    stream.put_back(first)
    if not match(stream, '#\\'):
        return None
    for charname, ascii in [('alarm', 7),
                            ('backspace', 8),
                            ('delete', 127),
                            ('escape', 27),
                            ('newline', 10),
                            ('null', 0),
                            ('return', 13),
                            ('space', 32),
                            ('tab', 9)]:
        if match(stream, charname):
            c = chr(ascii)
            break
    else:
        _, _, _, c = stream.read_char()
    return filename, line, col, 'character', c


def number(stream):
    first = filename, line, col, c = stream.read_char()
    if c not in first_number_char:
        stream.put_back(first)
        return None
    ret = [first]
    try:
        while True:
            next = stream.read_char()
            if next[-1] in rest_number_char:
                ret.append(next)
            else:
                stream.put_back(next)
                break
    except EOFError:
        pass
    s = ''.join(each[-1] for each in ret)
    if any(c for c in s if c in string.digits):
        ndots = s.count(".")
        if ndots == 0:
            return filename, line, col, 'fixnum', int(s)
        elif ndots == 1:
            return filename, line, col, 'flonum', float(s)
    for each in reversed(ret):
        stream.put_back(each)
    return None

def boolean(stream):
    first = filename, line, col, c = stream.read_char()
    if c != '#':
        stream.put_back(first)
        return None
    second = _, _, _, c = stream.read_char()
    if c == 't':
        return filename, line, col, 'boolean', True
    elif c == 'f':
        return filename, line, col, 'boolean', False
    else:
        stream.put_back(second)
        stream.put_back(first)
        return None

def identifier(stream):
    first = filename, line, col, c = stream.read_char()
    stream.put_back(first)
    chars = []
    try:
        while True:
            next = _, _, _, c = stream.read_char()
            if c in identifier_chars:
                chars.append(c)
            else:
                stream.put_back(next)
                break
    except EOFError:
        pass
    if not chars:
        return None
    name = ''.join(char[-1] for char in chars)
    if name == '.':
        return filename, line, col, '.', '.'
    elif name.startswith('.'):
        # It would be easier to just support names starting with '.', but
        # the R-1RK explicitly forbids them, so we reserve them at least
        # for the time being.
        for char in reversed(chars):
            stream.put_back(char)
        return None
    else:
        return filename, line, col, 'identifier', name


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
    check_not_token('. with something after', '.blah')
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
