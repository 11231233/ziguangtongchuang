"""Validate operator-entered board numbers without guessing physical values."""
import math
import re
import unicodedata


class BoardInputError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def normalized(text):
    return unicodedata.normalize('NFKC', str(text)).strip()


def parse_inner_corners(cols_text, rows_text):
    values = []
    for field, label, text, example in [('cols', '内角点列', cols_text, '9'),
                                        ('rows', '内角点行', rows_text, '6')]:
        text = normalized(text)
        if not re.fullmatch(r'[0-9]+', text):
            raise BoardInputError(field,
                f'“{label}”请填写整数，例如 {example}。当前输入：{text!r}。\n'
                '请全选该输入框后重新输入数字，不要带引号、反引号或单位。')
        try:
            value = int(text)
        except ValueError:
            raise BoardInputError(field, f'“{label}”数值过长，请按棋盘的实际内角点数量填写。') from None
        if value < 3:
            raise BoardInputError(field, f'“{label}”至少为3，请填写实际内角点数量。')
        values.append(value)
    return tuple(values)


def parse_board_inputs(cols_text, rows_text, square_text):
    cols, rows = parse_inner_corners(cols_text, rows_text)
    text = normalized(square_text)
    try:
        square = float(text)
    except ValueError:
        raise BoardInputError('square',
            '“实测格边/mm”请填写尺量的单格边长，只填数字，不带mm或毫米。\n'
            '支持小数点，例如实测20.5毫米时填写20.5。') from None
    if not math.isfinite(square) or square <= 0:
        raise BoardInputError('square', '“实测格边/mm”必须是大于0的有限数值，请填写实际测量结果。')
    return cols, rows, square
