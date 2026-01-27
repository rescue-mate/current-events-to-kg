# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

class Reference:
    def __init__(self, nr: int, url: str, anchor_text: str):
        self.url: str = url
        self.nr: int = nr
        self.anchor_text: str = anchor_text
