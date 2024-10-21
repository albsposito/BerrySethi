from kivy.config import Config
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '600')

from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.image import Image
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.textfield import MDTextField
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivymd.toast import toast
import graphviz
from graphviz import Digraph
import os

class RegexNode:
    def __init__(self, type, left=None, right=None, symbol=None):
        self.type = type
        self.left = left
        self.right = right
        self.symbol = symbol
        self.nullable = False
        self.firstpos = set()
        self.lastpos = set()
        self.position = None

class RegexParser:
    def __init__(self, regex):
        self.regex = regex
        self.pos = 0
        self.current_char = self.regex[self.pos] if self.regex else None

    def advance(self):
        self.pos += 1
        self.current_char = self.regex[self.pos] if self.pos < len(self.regex) else None

    def parse(self):
        node = self.expression()
        # Append '#' to mark the end
        hash_node = RegexNode('symbol', symbol='#')
        node = RegexNode('concat', left=node, right=hash_node)
        return node

    def expression(self):
        node = self.term()
        while self.current_char == '|':
            self.advance()
            node = RegexNode('union', left=node, right=self.term())
        return node

    def term(self):
        node = self.factor()
        while self.current_char and self.current_char not in ['|', ')']:
            node = RegexNode('concat', left=node, right=self.factor())
        return node

    def factor(self):
        node = self.base()
        while self.current_char in ['*', '+']:
            if self.current_char == '*':
                self.advance()
                node = RegexNode('star', left=node)
            elif self.current_char == '+':
                self.advance()
                # `a+` is equivalent to `a a*`
                node = RegexNode('concat', left=node, right=RegexNode('star', left=node))
        return node

    def base(self):
        if self.current_char == '(':
            self.advance()
            node = self.expression()
            if self.current_char != ')':
                raise Exception('Mismatched parentheses')
            self.advance()
            return node
        elif self.current_char and (self.current_char.isalnum() or self.current_char == '#'):
            symbol = self.current_char
            self.advance()
            return RegexNode('symbol', symbol=symbol)
        else:
            raise Exception(f'Unexpected character: {self.current_char}')

position_counter = 1
positions = {}

def annotate(node):
    global position_counter
    if node.type == 'symbol':
        node.nullable = False
        node.firstpos = {position_counter}
        node.lastpos = {position_counter}
        node.position = position_counter
        positions[position_counter] = node.symbol
        position_counter += 1
    else:
        left = node.left
        right = node.right
        if left:
            annotate(left)
        if right:
            annotate(right)

        if node.type == 'concat':
            node.nullable = left.nullable and right.nullable
            node.firstpos = left.firstpos if not left.nullable else left.firstpos.union(right.firstpos)
            node.lastpos = right.lastpos if not right.nullable else left.lastpos.union(right.lastpos)
        elif node.type == 'union':
            node.nullable = left.nullable or right.nullable
            node.firstpos = left.firstpos.union(right.firstpos)
            node.lastpos = left.lastpos.union(right.lastpos)
        elif node.type == 'star':
            node.nullable = True
            node.firstpos = left.firstpos
            node.lastpos = left.lastpos

def compute_followpos(node, followpos_table):
    if node.type == 'concat':
        for pos in node.left.lastpos:
            followpos_table.setdefault(pos, set()).update(node.right.firstpos)
    elif node.type == 'star':
        for pos in node.lastpos:
            followpos_table.setdefault(pos, set()).update(node.firstpos)

    if node.left:
        compute_followpos(node.left, followpos_table)
    if node.right:
        compute_followpos(node.right, followpos_table)

def construct_dfa(root, followpos_table):
    from collections import deque

    states = []
    state_pos = {}
    pos_state = {}

    queue = deque()

    start_pos = frozenset(root.firstpos)
    start_state_id = 0
    states.append({})
    state_pos[start_state_id] = start_pos
    pos_state[start_pos] = start_state_id
    queue.append(start_state_id)

    accepting_states = set()
    if any(positions[pos] == '#' for pos in start_pos):
        accepting_states.add(start_state_id)

    while queue:
        state_id = queue.popleft()
        pos_set = state_pos[state_id]

        symbol_pos_map = {}
        for pos in pos_set:
            symbol = positions[pos]
            if symbol != '#':
                symbol_pos_map.setdefault(symbol, set()).update(followpos_table.get(pos, set()))

        for symbol, next_pos_set in symbol_pos_map.items():
            next_pos_frozen = frozenset(next_pos_set)
            if next_pos_frozen in pos_state:
                next_state_id = pos_state[next_pos_frozen]
            else:
                next_state_id = len(states)
                states.append({})
                state_pos[next_state_id] = next_pos_frozen
                pos_state[next_pos_frozen] = next_state_id
                queue.append(next_state_id)
                if any(positions[pos] == '#' for pos in next_pos_set):
                    accepting_states.add(next_state_id)
            states[state_id][symbol] = next_state_id

    return states, accepting_states

def visualize_dfa(states, accepting_states, image_path):
    dot = Digraph(comment='DFA')

    # Add states and transitions
    for state_id, transitions in enumerate(states):
        shape = 'doublecircle' if state_id in accepting_states else 'circle'
        dot.node(str(state_id), shape=shape)

        for symbol, next_state in transitions.items():
            dot.edge(str(state_id), str(next_state), label=symbol)

    # Render the graph to the specified image path
    directory = os.path.dirname(image_path)
    if not os.path.exists(directory):
        os.makedirs(directory)
    dot.render(image_path, format='png', cleanup=True)

class MainApp(MDApp):
    def build(self):
        self.title = "Regular Expression to DFA"
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.primary_hue = "500"
        # self.theme_cls.material_style = "M3"  # Uncomment if supported
        return Builder.load_file('main.kv')

    def generate_dfa(self):
        regex = self.root.ids.regex_input.text
        try:
            # Reset global variables
            global position_counter, positions
            position_counter = 1
            positions = {}

            parser = RegexParser(regex)
            root = parser.parse()
            annotate(root)
            followpos_table = {}
            compute_followpos(root, followpos_table)
            states, accepting_states = construct_dfa(root, followpos_table)
            dfa_image_path = visualize_dfa(states, accepting_states)

            # Load and display the image
            if os.path.exists(dfa_image_path):
                self.root.ids.dfa_image.source = dfa_image_path
                self.root.ids.dfa_image.reload()
        except Exception as e:
            toast(f"Invalid regular expression: {e}")

if __name__ == '__main__':
    MainApp().run()
