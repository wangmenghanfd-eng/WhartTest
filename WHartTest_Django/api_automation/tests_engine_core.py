"""核心引擎能力(强类型断言 / JMESPath / 自定义函数 / 参数化)的纯函数单元测试。

均为无 DB 依赖的 SimpleTestCase，可离线快速运行：
    python manage.py test api_automation.tests_engine_core
"""
from django.test import SimpleTestCase

from api_automation import services


class CompareTests(SimpleTestCase):
    def test_eq_type_aware_and_backward_compatible(self):
        # 类型感知：数值相等
        self.assertTrue(services._compare(200, "eq", 200))
        self.assertTrue(services._compare(0, "eq", 0.0))
        # 向后兼容：字符串与数字仍相等(历史用例 "200" 对 200)
        self.assertTrue(services._compare("200", "eq", 200))
        self.assertTrue(services._compare(200, "eq", "200"))
        # bool 不被数字误判
        self.assertTrue(services._compare(True, "eq", True))
        self.assertFalse(services._compare(True, "eq", "True") is True and services._compare(True, "eq", 1))

    def test_operator_alias_normalization(self):
        self.assertTrue(services._compare(1, "equals", 1))
        self.assertTrue(services._compare(1, "==", 1))
        self.assertTrue(services._compare(2, "greater_than", 1))
        self.assertTrue(services._compare([1, 2, 3], "len_eq", 3))
        self.assertTrue(services._compare("abc", "length_equal", 3))

    def test_new_operators(self):
        self.assertTrue(services._compare("hello", "str_eq", "hello"))
        self.assertTrue(services._compare([1, 2], "type_match", "array"))
        self.assertTrue(services._compare({"a": 1}, "type_match", "object"))
        self.assertTrue(services._compare(None, "type_match", "null"))
        self.assertTrue(services._compare("abcdef", "startswith", "abc"))
        self.assertTrue(services._compare("abcdef", "endswith", "def"))
        self.assertTrue(services._compare("b", "contained_by", ["a", "b", "c"]))
        self.assertTrue(services._compare([1, 2, 3], "length_gt", 2))
        self.assertTrue(services._compare([1, 2, 3], "length_lt", 4))
        self.assertTrue(services._compare([1, 2, 3], "length_ge", 3))
        self.assertTrue(services._compare([1, 2, 3], "length_le", 3))
        self.assertFalse(services._compare([1], "length_eq", 3))

    def test_existing_operators_unchanged(self):
        self.assertTrue(services._compare("hello world", "contains", "world"))
        self.assertTrue(services._compare("hello", "not_contains", "xyz"))
        self.assertTrue(services._compare("2026-01-01", "regex", r"\d{4}-\d{2}-\d{2}"))
        self.assertTrue(services._compare(3, "in", [1, 2, 3]))
        self.assertTrue(services._compare(5, "gt", 3))
        self.assertTrue(services._compare(None, "is_empty", None))
        self.assertTrue(services._compare("x", "is_not_empty", None))


class ResolvePathTests(SimpleTestCase):
    def setUp(self):
        self.body = {
            "data": {"token": "abc", "items": [{"id": 1, "vip": True}, {"id": 2, "vip": False}]},
            "code": 0,
            "with-hyphen": 42,
        }

    def test_simple_dot_path_via_jmespath(self):
        self.assertEqual(services._resolve_path(self.body, "data.token"), "abc")
        self.assertEqual(services._resolve_path(self.body, "data.items[0].id"), 1)
        self.assertEqual(services._resolve_path(self.body, "code"), 0)

    def test_legacy_dollar_prefix_compatible(self):
        self.assertEqual(services._resolve_path(self.body, "$.data.token"), "abc")
        self.assertEqual(services._resolve_path(self.body, "$data.token"), "abc")

    def test_jmespath_filter_expression(self):
        # JMESPath 高级能力：过滤 vip==true 的 id
        self.assertEqual(services._resolve_path(self.body, "data.items[?vip].id"), [1])

    def test_empty_expr_returns_whole(self):
        self.assertEqual(services._resolve_path(self.body, ""), self.body)

    def test_hyphen_key_falls_back_to_legacy(self):
        # 连字符键名 JMESPath 无法直接解析 -> 回退旧点路径解析器
        self.assertEqual(services._resolve_path(self.body, "with-hyphen"), 42)


class RenderValueFunctionTests(SimpleTestCase):
    def setUp(self):
        self.functions = {
            "add_one": lambda x: int(x) + 1,
            "greet": lambda name: f"hi-{name}",
            "now_ts": lambda: 1234,
        }
        self.variables = {"n": 5, "user": "bob"}

    def test_variable_only_unchanged(self):
        # 无 functions 时行为不变
        self.assertEqual(services._render_value("${{user}}", self.variables), "bob")
        self.assertEqual(services._render_value("${{n}}", self.variables), 5)

    def test_whole_function_call_preserves_type(self):
        self.assertEqual(services._render_value("${{now_ts()}}", self.variables, self.functions), 1234)
        self.assertEqual(services._render_value("${{add_one($n)}}", self.variables, self.functions), 6)

    def test_mixed_function_in_string(self):
        self.assertEqual(
            services._render_value("token-${{greet($user)}}-end", self.variables, self.functions),
            "token-hi-bob-end",
        )

    def test_function_with_literal_args(self):
        self.assertEqual(services._render_value("${{add_one(41)}}", self.variables, self.functions), 42)
        self.assertEqual(services._render_value("${{greet('kate')}}", self.variables, self.functions), "hi-kate")

    def test_missing_function_raises(self):
        with self.assertRaises(ValueError):
            services._render_value("${{no_such_fn()}}", self.variables, self.functions)

    def test_nested_dict_and_list_rendering(self):
        rendered = services._render_value(
            {"a": "${{add_one($n)}}", "b": ["${{user}}", "${{now_ts()}}"]},
            self.variables,
            self.functions,
        )
        self.assertEqual(rendered, {"a": 6, "b": ["bob", 1234]})


class ArgSplitTests(SimpleTestCase):
    def test_split_top_level_respects_quotes_and_brackets(self):
        self.assertEqual(services._split_call_args("1, 2, 3"), ["1", "2", "3"])
        self.assertEqual(services._split_call_args("'a,b', [1,2]"), ["'a,b'", "[1,2]"])
        self.assertEqual(services._split_call_args(""), [])

    def test_eval_arg_variable_and_literal(self):
        variables = {"x": 9}
        self.assertEqual(services._eval_call_arg("${{x}}", variables), 9)
        self.assertEqual(services._eval_call_arg("$x", variables), 9)
        self.assertEqual(services._eval_call_arg("42", variables), 42)
        self.assertEqual(services._eval_call_arg("'hi'", variables), "hi")


class ParameterizeTests(SimpleTestCase):
    def test_single_param_inline_list(self):
        result = services._expand_parameters({"ver": ["v1", "v2"]})
        self.assertEqual(result, [{"ver": "v1"}, {"ver": "v2"}])

    def test_compound_name_zip(self):
        result = services._expand_parameters({"user-pwd": [["u1", "p1"], ["u2", "p2"]]})
        self.assertEqual(result, [{"user": "u1", "pwd": "p1"}, {"user": "u2", "pwd": "p2"}])

    def test_cartesian_product_of_two_params(self):
        result = services._expand_parameters({"a": [1, 2], "b": ["x", "y"]})
        self.assertEqual(len(result), 4)
        self.assertIn({"a": 1, "b": "x"}, result)
        self.assertIn({"a": 2, "b": "y"}, result)

    def test_empty_returns_empty_list(self):
        self.assertEqual(services._expand_parameters({}), [])
        self.assertEqual(services._expand_parameters(None), [])

    def test_gen_cartesian_product(self):
        out = services._gen_cartesian_product([{"a": 1}, {"a": 2}], [{"b": 3}])
        self.assertEqual(out, [{"a": 1, "b": 3}, {"a": 2, "b": 3}])
