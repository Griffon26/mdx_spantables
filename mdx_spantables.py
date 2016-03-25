"""
SpanTables Extension for Python-Markdown
========================================

This is a slightly modified version of the tables extension that comes with
python-markdown.

To span cells across multiple columns make sure the cells end with multiple
consecutive vertical bars. To span cells across rows fill the cell on the last
row with at least one underscore at the start or end of its content and no
other characters than spaces or underscores.

For example:

    | head1           | head2 |
    |-----------------|-------|
    | span two cols          ||
    | span two rows   |       |
    |_                |       |

See <https://pythonhosted.org/Markdown/extensions/tables.html>
for documentation of the original extension.

Original code Copyright 2009 [Waylan Limberg](http://achinghead.com)
SpanTables changes Copyright 2016 [Maurice van der Pot](griffon26@kfk4ever.com)

License: [BSD](http://www.opensource.org/licenses/bsd-license.php)

"""

from __future__ import unicode_literals
from markdown.blockprocessors import BlockProcessor
from markdown.extensions import Extension
from markdown.inlinepatterns import BacktickPattern, BACKTICK_RE
from markdown.util import etree


class SpanTableProcessor(BlockProcessor):
    """ Process Tables. """

    def test(self, parent, block):
        rows = block.split('\n')
        return (len(rows) > 1 and '|' in rows[0] and
                '|' in rows[1] and '-' in rows[1] and
                rows[1].strip()[0] in ['|', ':', '-'])


    def is_end_of_rowspan(self, td):
        return ((td != None) and
                (td.text.startswith('_') or td.text.endswith('_')) and
                (td.text.strip('_ ') == ''))

    def apply_rowspans(self, tbody):
            table_cells = {}

            rows = tbody.findall('tr')
            max_cols = 0
            max_rows = len(rows)
            for y, tr in enumerate(rows):

                cols = tr.findall('td')

                x = 0
                for td in cols:

                    colspan = int(td.get('colspan', default='1'))

                    # Insert the td together with its parent
                    table_cells[(x, y)] = (tr, td)

                    x += colspan

                max_cols = max(max_cols, x)

            for x in range(max_cols):
                possible_cells_in_rowspan = 0
                current_colspan = None

                for y in range(max_rows):
                    _, td = table_cells.get((x, y), (None, None))

                    if td == None:
                        possible_cells_in_rowspan = 0

                    else:
                        colspan = td.get('colspan')
                        if colspan != current_colspan:
                            current_colspan = colspan
                            possible_cells_in_rowspan = 0

                        if not td.text:
                            possible_cells_in_rowspan += 1

                        elif self.is_end_of_rowspan(td):
                            td.text = ''
                            possible_cells_in_rowspan += 1
                            first_cell_of_rowspan_y = y - (possible_cells_in_rowspan - 1)
                            for del_y in range(y, first_cell_of_rowspan_y, -1):
                                tr, td = table_cells.get((x, del_y))
                                tr.remove(td)
                            _, first_cell = table_cells.get((x, first_cell_of_rowspan_y))
                            first_cell.set('rowspan', str(possible_cells_in_rowspan))

                            possible_cells_in_rowspan = 0

                        else:
                            possible_cells_in_rowspan = 1

    def run(self, parent, blocks):
        """ Parse a table block and build table. """
        block = blocks.pop(0).split('\n')
        header = block[0].strip()
        seperator = block[1].strip()
        rows = [] if len(block) < 3 else block[2:]
        # Get format type (bordered by pipes or not)
        border = False
        if header.startswith('|'):
            border = True
        # Get alignment of columns
        align = []
        for c in self._split_row(seperator, border):
            if c.startswith(':') and c.endswith(':'):
                align.append('center')
            elif c.startswith(':'):
                align.append('left')
            elif c.endswith(':'):
                align.append('right')
            else:
                align.append(None)
        # Build table
        table = etree.SubElement(parent, 'table')
        thead = etree.SubElement(table, 'thead')
        self._build_row(header, thead, align, border)
        tbody = etree.SubElement(table, 'tbody')
        for row in rows:
            self._build_row(row.strip(), tbody, align, border)

        self.apply_rowspans(tbody)

    def _build_row(self, row, parent, align, border):
        """ Given a row of text, build table cells. """
        tr = etree.SubElement(parent, 'tr')
        tag = 'td'
        if parent.tag == 'thead':
            tag = 'th'
        cells = self._split_row(row, border)
        c = None
        # We use align here rather than cells to ensure every row
        # contains the same number of columns.
        for i, a in enumerate(align):

            # After this None indicates that the cell before it should span
            # this column and '' indicates an cell without content
            try:
                text = cells[i]
                if text == '':
                    text = None
            except IndexError:  # pragma: no cover
                text = ''

            # No text after split indicates colspan
            if text == None:
                if c is not None:
                    colspan = int(c.get('colspan', default='1'))
                    c.set('colspan', str(colspan + 1))
                else:
                    # if this is the first cell, then fall back to creating an empty cell
                    text = ''

            if text != None:
                c = etree.SubElement(tr, tag)
                c.text = text.strip()

            if a:
                c.set('align', a)

    def _split_row(self, row, border):
        """ split a row of text into list of cells. """
        if border:
            if row.startswith('|'):
                row = row[1:]
            if row.endswith('|'):
                row = row[:-1]
        return self._split(row, '|')

    def _split(self, row, marker):
        """ split a row of text with some code into a list of cells. """
        if self._row_has_unpaired_backticks(row):
            # fallback on old behaviour
            return row.split(marker)
        # modify the backtick pattern to only match at the beginning of the search string
        backtick_pattern = BacktickPattern('^' + BACKTICK_RE)
        elements = []
        current = ''
        i = 0
        while i < len(row):
            letter = row[i]
            if letter == marker:
                if current != '' or len(elements) == 0:
                    # Don't append empty string unless it is the first element
                    # The border is already removed when we get the row, then the line is strip()'d
                    # If the first element is a marker, then we have an empty first cell
                    elements.append(current)
                current = ''
            else:
                match = backtick_pattern.getCompiledRegExp().match(row[i:])
                if not match:
                    current += letter
                else:
                    groups = match.groups()
                    delim = groups[1]  # the code block delimeter (ie 1 or more backticks)
                    row_contents = groups[2]  # the text contained inside the code block
                    i += match.start(4) - 1  # jump pointer to the beginning of the rest of the text (group #4)
                    element = delim + row_contents + delim  # reinstert backticks
                    current += element
            i += 1
        elements.append(current)
        return elements

    def _row_has_unpaired_backticks(self, row):
        count_total_backtick = row.count('`')
        count_escaped_backtick = row.count('\`')
        count_backtick = count_total_backtick - count_escaped_backtick
        # odd number of backticks,
        # we won't be able to build correct code blocks
        return count_backtick & 1


class TableExtension(Extension):
    """ Add tables to Markdown. """

    def extendMarkdown(self, md, md_globals):
        """ Add an instance of SpanTableProcessor to BlockParser. """
        md.parser.blockprocessors.add('spantable',
                                      SpanTableProcessor(md.parser),
                                      '_begin')


def makeExtension(*args, **kwargs):
    return TableExtension(*args, **kwargs)
