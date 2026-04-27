import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from rest_framework.test import APIClient

from projects.models import Project
from testcase_templates.models import ImportExportTemplate
from testcases.models import TestCase as TestCaseModel


class TestCaseImportExcelViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin123456",
        )
        self.client.force_authenticate(self.user)
        self.project = Project.objects.create(
            name="导入测试项目",
            description="用于验证 Excel 导入接口",
            creator=self.user,
        )
        self.url = f"/api/projects/{self.project.id}/testcases/import-excel/"

    def _build_excel_file(self, filename="testcases.xlsx"):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "测试用例"
        worksheet.append(
            ["用例名称", "所属模块", "前置条件", "步骤描述", "预期结果", "用例等级", "备注"]
        )
        worksheet.append(
            [
                "登录失败-错误密码",
                "/用户登录模块",
                "系统URL: https://practice.expandtesting.com/login",
                "[1]访问登录页\n[2]输入错误密码",
                "[1]登录页显示正确\n[2]系统提示密码错误",
                "P1",
                "异常流程导入验证",
            ]
        )

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return SimpleUploadedFile(
            filename,
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_import_excel_rejects_export_only_template(self):
        template = ImportExportTemplate.objects.create(
            name="仅导出模板",
            template_type="export",
            sheet_name="测试用例",
            header_row=1,
            data_start_row=2,
            field_mappings={
                "name": "用例名称",
                "module": "所属模块",
            },
            step_parsing_mode="single_cell",
            module_path_delimiter="/",
            is_active=True,
            creator=self.user,
        )

        response = self.client.post(
            self.url,
            {"file": self._build_excel_file(), "template_id": template.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("不是可用于导入的模版", response.data["error"])

    def test_import_excel_accepts_both_template(self):
        template = ImportExportTemplate.objects.create(
            name="标准导入导出模板",
            template_type="both",
            description="用于测试 both 类型模板可正常导入",
            sheet_name="测试用例",
            template_headers=[
                "用例名称",
                "所属模块",
                "前置条件",
                "步骤描述",
                "预期结果",
                "用例等级",
                "备注",
            ],
            header_row=1,
            data_start_row=2,
            field_mappings={
                "name": "用例名称",
                "module": "所属模块",
                "precondition": "前置条件",
                "steps": "步骤描述",
                "expected_results": "预期结果",
                "level": "用例等级",
                "notes": "备注",
            },
            value_transformations={},
            step_parsing_mode="single_cell",
            step_config={
                "step_column": "步骤描述",
                "expected_column": "预期结果",
            },
            module_path_delimiter="/",
            is_active=True,
            creator=self.user,
        )

        response = self.client.post(
            self.url,
            {"file": self._build_excel_file(), "template_id": template.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["imported_count"], 1)
        self.assertTrue(
            TestCaseModel.objects.filter(
                project=self.project,
                name="登录失败-错误密码",
            ).exists()
        )
