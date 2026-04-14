package com.dawnchat.app.ui.main

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import coil.load
import com.dawnchat.app.R
import com.dawnchat.app.auth.MobileAuthRepository
import com.dawnchat.app.auth.NativeLoginActivity
import com.dawnchat.app.auth.UserProfileSnapshot
import com.dawnchat.app.ui.about.AboutActivity
import com.dawnchat.app.ui.profile.ProfileActivity
import com.dawnchat.app.ui.settings.SettingsActivity
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.card.MaterialCardView
import com.google.android.material.imageview.ShapeableImageView
import kotlinx.coroutines.launch

class MineFragment : Fragment() {

    private var headerPrimary: TextView? = null
    private var headerSecondary: TextView? = null
    private var headerAvatar: ShapeableImageView? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View {
        return inflater.inflate(R.layout.fragment_mine, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val toolbar = view.findViewById<MaterialToolbar>(R.id.toolbarMine)
        toolbar.title = getString(R.string.tab_mine)

        headerPrimary = view.findViewById(R.id.textMinePrimary)
        headerSecondary = view.findViewById(R.id.textMineSecondary)
        headerAvatar = view.findViewById(R.id.imageMineAvatar)

        val profileCard = view.findViewById<MaterialCardView>(R.id.cardProfile)
        val settingsCard = view.findViewById<MaterialCardView>(R.id.cardSettings)
        val aboutCard = view.findViewById<MaterialCardView>(R.id.cardAbout)
        val logoutCard = view.findViewById<MaterialCardView>(R.id.cardLogout)

        profileCard.setOnClickListener {
            startActivity(Intent(requireContext(), ProfileActivity::class.java))
        }
        settingsCard.setOnClickListener {
            startActivity(Intent(requireContext(), SettingsActivity::class.java))
        }
        aboutCard.setOnClickListener {
            startActivity(Intent(requireContext(), AboutActivity::class.java))
        }
        logoutCard.setOnClickListener {
            viewLifecycleOwner.lifecycleScope.launch {
                MobileAuthRepository(requireContext()).clearSession()
                startActivity(
                    Intent(requireActivity(), NativeLoginActivity::class.java).apply {
                        addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK)
                    },
                )
                requireActivity().finish()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        val primary = headerPrimary ?: return
        val secondary = headerSecondary ?: return
        val avatar = headerAvatar ?: return
        viewLifecycleOwner.lifecycleScope.launch {
            val repo = MobileAuthRepository(requireContext())
            val snapshot = repo.loadProfileForUi()
            applyProfile(snapshot, primary, secondary, avatar)
        }
    }

    private fun applyProfile(
        snapshot: UserProfileSnapshot?,
        primary: TextView,
        secondary: TextView,
        avatar: ShapeableImageView,
    ) {
        if (snapshot == null) {
            primary.text = getString(R.string.mine_user_fallback)
            secondary.text = ""
            avatar.setImageResource(R.drawable.ic_avatar_placeholder)
            return
        }
        val primaryText = snapshot.displayName?.takeIf { it.isNotBlank() }
            ?: snapshot.email?.takeIf { it.isNotBlank() }
            ?: getString(R.string.mine_user_fallback)
        primary.text = primaryText
        secondary.text = snapshot.email?.takeIf { it.isNotBlank() }
            ?: snapshot.id.take(12).let { "$it…" }
        val url = snapshot.avatarUrl?.trim()?.takeIf { it.isNotEmpty() }
        if (url != null) {
            avatar.load(url) {
                placeholder(R.drawable.ic_avatar_placeholder)
                error(R.drawable.ic_avatar_placeholder)
            }
        } else {
            avatar.setImageResource(R.drawable.ic_avatar_placeholder)
        }
    }

    companion object {
        const val TAG = "MineFragment"
    }
}
