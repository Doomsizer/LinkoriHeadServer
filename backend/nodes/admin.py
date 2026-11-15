@admin.register(VpnNode)
class VpnNodeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "country_code",
        "flag_emoji",
        "ip_address",
        "auth_type",
        "is_enabled",
        "priority",
        "updated_at",
    )
    list_filter = ("is_enabled", "country_code")
    search_fields = ("name", "country_code", "ip_address", "panel_url")
    ordering = ("priority", "name")
    inlines = (NodeInboundInline,)
    fieldsets = (
        (
            "Основное",
            {"fields": ("name", "country_code", "flag_emoji", "ip_address", "is_enabled", "priority")},
        ),
        (
            "Подключение к 3x-ui",
            {
                "fields": ("panel_url", "panel_api_token", "panel_username", "panel_password"),
            },
        ),
    )

    @admin.display(description="Авторизация")
    def auth_type(self, obj):
        if obj.panel_api_token:
            return "API Token"
        if obj.panel_username:
            return "Login/Pass"
        return "Не задана"