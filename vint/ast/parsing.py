import extlib.vimlparser
import chardet
import re
from vint.ast.traversing import traverse


class EncodingDetectionError(Exception):
    def __init__(self, file_path):
        self.file_path = file_path


    def __str__(self):
        return 'Cannot detect encoding (binary file?): {file_path}'.format(
            file_path=str(self.file_path))


class Parser(object):
    def __init__(self, plugins=None):
        """ Initialize Parser with the specified plugins.
        The plugins can add attributes to the AST.
        """
        self.plugins = plugins.values() if plugins else []


    def parse(self, string):
        """ Parse vim script string and return the AST. """
        lines = string.split('\n')

        reader = extlib.vimlparser.StringReader(lines)
        parser = extlib.vimlparser.VimLParser()
        ast = parser.parse(reader)

        # TOPLEVEL does not have a pos, but we need pos for all nodes
        ast['pos'] = {'col': 1, 'i': 0, 'lnum': 1}

        for plugin in self.plugins:
            plugin.process(ast)

        return ast


    def parse_file(self, file_path):
        """ Parse vim script file and return the AST. """
        with file_path.open(mode='rb') as f:
            bytes_seq = f.read()
            encoding_hint = chardet.detect(bytes_seq)

            encoding = encoding_hint['encoding']
            if not encoding:
                # Falsey means we cannot detect the encoding of the file.
                raise EncodingDetectionError(file_path)

            decoded = bytes_seq.decode(encoding)

            decoded_and_lf_normalized = decoded.replace('\r\n', '\n')

            return self.parse(decoded_and_lf_normalized)


    def parse_redir(self, redir_cmd):
        """ Parse a command :redir content. """
        redir_cmd_str = redir_cmd['str']

        matched = re.match(r'redir?!?\s*(=>>?\s*)(\S+)', redir_cmd_str)
        if matched:
            redir_cmd_op = matched.group(1)
            redir_cmd_body = matched.group(2)

            arg_pos = redir_cmd['ea']['argpos']

            # Position of the "redir_cmd_body"
            start_pos = {
                'col': arg_pos['col'] + len(redir_cmd_op),
                'i': arg_pos['i'] + len(redir_cmd_op),
                'lnum': arg_pos['lnum'],
            }

            # NOTE: This is a hack to parse variable node.
            raw_ast = self.parse('echo ' + redir_cmd_body)

            # We need the left node of ECHO node
            redir_cmd_ast = raw_ast['body'][0]['list'][0]

            def adjust_position(node):
                pos = node['pos']
                # Care 1-based index and the length of "echo ".
                pos['col'] += start_pos['col'] - 1 - 5

                # Care the length of "echo ".
                pos['i'] += start_pos['i'] - 5

                # Care 1-based index
                pos['lnum'] += start_pos['lnum'] - 1

            traverse(redir_cmd_ast, on_enter=adjust_position)

            return redir_cmd_ast

        return None
