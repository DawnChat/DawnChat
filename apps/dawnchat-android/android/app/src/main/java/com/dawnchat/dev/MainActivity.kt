package com.dawnchat.dev

import android.content.Context
import android.os.Bundle
import androidx.appcompat.app.AppCompatDelegate
import androidx.appcompat.app.AppCompatActivity
import androidx.core.os.LocaleListCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.fragment.app.Fragment
import com.dawnchat.dev.ui.main.HomeFragment
import com.dawnchat.dev.ui.main.MineFragment
import com.google.android.material.bottomnavigation.BottomNavigationView

class MainActivity : AppCompatActivity() {

    private var currentTabId: Int = R.id.nav_home

    override fun onCreate(savedInstanceState: Bundle?) {
        applySavedAppearance()
        installSplashScreen()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val bottomNavigation = findViewById<BottomNavigationView>(R.id.bottomNavigation)
        bottomNavigation.setOnItemSelectedListener { item ->
            if (item.itemId != currentTabId) {
                currentTabId = item.itemId
                when (item.itemId) {
                    R.id.nav_home -> switchFragment(HomeFragment(), HomeFragment.TAG)
                    R.id.nav_mine -> switchFragment(MineFragment(), MineFragment.TAG)
                    else -> false
                }
            } else {
                true
            }
        }

        if (savedInstanceState == null) {
            switchFragment(HomeFragment(), HomeFragment.TAG)
            bottomNavigation.selectedItemId = R.id.nav_home
        } else {
            currentTabId = bottomNavigation.selectedItemId
        }
    }

    private fun switchFragment(fragment: Fragment, tag: String): Boolean {
        supportFragmentManager.beginTransaction()
            .replace(R.id.mainContainer, fragment, tag)
            .commit()
        return true
    }

    private fun applySavedAppearance() {
        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val theme = prefs.getString(KEY_THEME, THEME_SYSTEM)
        AppCompatDelegate.setDefaultNightMode(
            when (theme) {
                THEME_LIGHT -> AppCompatDelegate.MODE_NIGHT_NO
                THEME_DARK -> AppCompatDelegate.MODE_NIGHT_YES
                else -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
            }
        )

        val language = prefs.getString(KEY_LANGUAGE, LANG_SYSTEM)
        val locales = when (language) {
            LANG_ZH -> LocaleListCompat.forLanguageTags("zh-CN")
            LANG_EN -> LocaleListCompat.forLanguageTags("en")
            else -> LocaleListCompat.getEmptyLocaleList()
        }
        AppCompatDelegate.setApplicationLocales(locales)
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