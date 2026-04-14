package com.dawnchat.app.ui.settings

import android.content.Context
import android.os.Bundle
import android.widget.RadioGroup
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import com.dawnchat.app.R
import com.dawnchat.app.builtin.HostBuiltinAssistantPrefs
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.switchmaterial.SwitchMaterial

class SettingsActivity : AppCompatActivity() {

    private val prefs by lazy { getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbarSettings)
        toolbar.title = getString(R.string.page_settings)
        toolbar.setNavigationOnClickListener { finish() }

        val themeGroup = findViewById<RadioGroup>(R.id.groupTheme)
        val languageGroup = findViewById<RadioGroup>(R.id.groupLanguage)

        bindTheme(themeGroup)
        bindAutoOpenAssistant()
        bindLanguage(languageGroup)
    }

    private fun bindAutoOpenAssistant() {
        val sw = findViewById<SwitchMaterial>(R.id.switchAutoOpenAssistant)
        sw.isChecked = prefs.getBoolean(HostBuiltinAssistantPrefs.KEY_AUTO_OPEN_ENABLED, true)
        sw.setOnCheckedChangeListener { _, checked ->
            prefs.edit().putBoolean(HostBuiltinAssistantPrefs.KEY_AUTO_OPEN_ENABLED, checked).apply()
            Toast.makeText(this, R.string.settings_applied, Toast.LENGTH_SHORT).show()
        }
    }

    private fun bindTheme(group: RadioGroup) {
        when (prefs.getString(KEY_THEME, THEME_SYSTEM)) {
            THEME_LIGHT -> group.check(R.id.radioThemeLight)
            THEME_DARK -> group.check(R.id.radioThemeDark)
            else -> group.check(R.id.radioThemeSystem)
        }

        group.setOnCheckedChangeListener { _, checkedId ->
            val mode = when (checkedId) {
                R.id.radioThemeLight -> THEME_LIGHT
                R.id.radioThemeDark -> THEME_DARK
                else -> THEME_SYSTEM
            }
            prefs.edit().putString(KEY_THEME, mode).apply()
            AppCompatDelegate.setDefaultNightMode(
                when (mode) {
                    THEME_LIGHT -> AppCompatDelegate.MODE_NIGHT_NO
                    THEME_DARK -> AppCompatDelegate.MODE_NIGHT_YES
                    else -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
                }
            )
            Toast.makeText(this, R.string.settings_applied, Toast.LENGTH_SHORT).show()
        }
    }

    private fun bindLanguage(group: RadioGroup) {
        when (prefs.getString(KEY_LANGUAGE, LANG_SYSTEM)) {
            LANG_ZH -> group.check(R.id.radioLangZh)
            LANG_EN -> group.check(R.id.radioLangEn)
            else -> group.check(R.id.radioLangSystem)
        }

        group.setOnCheckedChangeListener { _, checkedId ->
            val language = when (checkedId) {
                R.id.radioLangZh -> LANG_ZH
                R.id.radioLangEn -> LANG_EN
                else -> LANG_SYSTEM
            }
            prefs.edit().putString(KEY_LANGUAGE, language).apply()

            val locales = when (language) {
                LANG_ZH -> LocaleListCompat.forLanguageTags("zh-CN")
                LANG_EN -> LocaleListCompat.forLanguageTags("en")
                else -> LocaleListCompat.getEmptyLocaleList()
            }
            AppCompatDelegate.setApplicationLocales(locales)
            Toast.makeText(this, R.string.settings_applied, Toast.LENGTH_SHORT).show()
        }
    }

    companion object {
        private const val PREFS_NAME = "host_settings"
        private const val KEY_THEME = "theme"
        private const val KEY_LANGUAGE = "language"

        private const val THEME_SYSTEM = "system"
        private const val THEME_LIGHT = "light"
        private const val THEME_DARK = "dark"

        private const val LANG_SYSTEM = "system"
        private const val LANG_ZH = "zh"
        private const val LANG_EN = "en"
    }
}
