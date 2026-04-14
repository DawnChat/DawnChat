package com.dawnchat.app.ui.profile

import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.dawnchat.app.R
import com.dawnchat.app.auth.MobileAuthRepository
import com.dawnchat.app.auth.UserProfileSnapshot
import com.google.android.material.appbar.MaterialToolbar
import kotlinx.coroutines.launch

class ProfileActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_profile)
        val toolbar = findViewById<MaterialToolbar>(R.id.toolbarProfile)
        toolbar.title = getString(R.string.profile_title)
        toolbar.setNavigationIcon(androidx.appcompat.R.drawable.abc_ic_ab_back_material)
        toolbar.setNavigationOnClickListener { finish() }
    }

    override fun onResume() {
        super.onResume()
        lifecycleScope.launch {
            val snapshot = MobileAuthRepository(this@ProfileActivity).loadProfileForUi()
            bind(snapshot)
        }
    }

    private fun bind(s: UserProfileSnapshot?) {
        val empty = getString(R.string.profile_value_empty)
        findViewById<android.widget.TextView>(R.id.profileValueEmail).text =
            s?.email?.takeIf { it.isNotBlank() } ?: empty
        findViewById<android.widget.TextView>(R.id.profileValueUserId).text =
            s?.id?.takeIf { it.isNotBlank() } ?: empty
        val phone = s?.phone?.takeIf { it.isNotBlank() }
        val phoneRow = findViewById<View>(R.id.profileRowPhone)
        val phoneDivider = findViewById<View>(R.id.profileDividerPhone)
        if (phone != null) {
            phoneRow.visibility = View.VISIBLE
            phoneDivider.visibility = View.VISIBLE
            findViewById<android.widget.TextView>(R.id.profileValuePhone).text = phone
        } else {
            phoneRow.visibility = View.GONE
            phoneDivider.visibility = View.GONE
        }
        findViewById<android.widget.TextView>(R.id.profileValueDisplayName).text =
            s?.displayName?.takeIf { it.isNotBlank() } ?: empty
        findViewById<android.widget.TextView>(R.id.profileValueCreatedAt).text =
            s?.createdAtIso?.takeIf { it.isNotBlank() } ?: empty
        findViewById<android.widget.TextView>(R.id.profileValueLastSignIn).text =
            s?.lastSignInAtIso?.takeIf { it.isNotBlank() } ?: empty
    }
}
