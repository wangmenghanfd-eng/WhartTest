from django.db import migrations, models


def migrate_intelligent_case_generation_prompt(apps, schema_editor):
    UserPrompt = apps.get_model("prompts", "UserPrompt")
    UserPrompt.objects.filter(
        name="智能用例生成",
        prompt_type="general",
    ).update(prompt_type="test_case_generation")


def rollback_intelligent_case_generation_prompt(apps, schema_editor):
    UserPrompt = apps.get_model("prompts", "UserPrompt")
    UserPrompt.objects.filter(
        name="智能用例生成",
        prompt_type="test_case_generation",
    ).update(prompt_type="general")


class Migration(migrations.Migration):

    dependencies = [
        ("prompts", "0010_alter_userprompt_prompt_type"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="userprompt",
            name="unique_user_program_prompt_type",
        ),
        migrations.AlterField(
            model_name="userprompt",
            name="prompt_type",
            field=models.CharField(
                choices=[
                    ("general", "通用对话"),
                    ("completeness_analysis", "完整性分析"),
                    ("consistency_analysis", "一致性分析"),
                    ("testability_analysis", "可测性分析"),
                    ("feasibility_analysis", "可行性分析"),
                    ("clarity_analysis", "清晰度分析"),
                    ("logic_analysis", "逻辑分析"),
                    ("test_case_generation", "测试用例生成"),
                    ("test_case_execution", "测试用例执行"),
                    ("diagram_generation", "图表生成"),
                ],
                default="general",
                help_text="提示词的使用类型",
                max_length=50,
                verbose_name="提示词类型",
            ),
        ),
        migrations.RunPython(
            migrate_intelligent_case_generation_prompt,
            rollback_intelligent_case_generation_prompt,
        ),
        migrations.AddConstraint(
            model_name="userprompt",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    (
                        "prompt_type__in",
                        [
                            "completeness_analysis",
                            "consistency_analysis",
                            "testability_analysis",
                            "feasibility_analysis",
                            "clarity_analysis",
                            "logic_analysis",
                            "test_case_generation",
                            "test_case_execution",
                        ],
                    )
                ),
                fields=("user", "prompt_type"),
                name="unique_user_program_prompt_type",
            ),
        ),
    ]
