char_from_name = {'#\\alarm': '\a',
                  '#\\backspace': '\b',
                  '#\\delete': '\x7f',
                  '#\\escape': '\x1b',
                  '#\\newline': '\n',
                  '#\\null': '\x00',
                  '#\\return': '\r',
                  '#\\space': ' ',
                  '#\\tab': '\t'}

name_from_char = dict((v, k) for k, v in char_from_name.iteritems())
