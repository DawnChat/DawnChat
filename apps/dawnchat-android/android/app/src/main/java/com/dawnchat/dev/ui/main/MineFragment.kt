package com.dawnchat.dev.ui.main

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import com.dawnchat.dev.R
import com.dawnchat.dev.ui.about.AboutActivity
import com.dawnchat.dev.ui.settings.SettingsActivity
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.card.MaterialCardView

class MineFragment : Fragment() {

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

        val settingsCard = view.findViewById<MaterialCardView>(R.id.cardSettings)
        val aboutCard = view.findViewById<MaterialCardView>(R.id.cardAbout)

        settingsCard.setOnClickListener {
            startActivity(Intent(requireContext(), SettingsActivity::class.java))
        }
        aboutCard.setOnClickListener {
            startActivity(Intent(requireContext(), AboutActivity::class.java))
        }
    }

    companion object {
        const val TAG = "MineFragment"
    }
}
