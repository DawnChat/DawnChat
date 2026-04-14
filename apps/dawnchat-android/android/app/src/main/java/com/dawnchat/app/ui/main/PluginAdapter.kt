package com.dawnchat.app.ui.main

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.dawnchat.app.R
import com.dawnchat.app.data.plugin.PluginMetadata
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class PluginAdapter(
    private val onClick: (PluginMetadata) -> Unit,
) : RecyclerView.Adapter<PluginAdapter.PluginViewHolder>() {

    private val items = mutableListOf<PluginMetadata>()
    private val formatter = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault())

    fun submitList(newItems: List<PluginMetadata>) {
        items.clear()
        items.addAll(newItems)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): PluginViewHolder {
        val inflater = LayoutInflater.from(parent.context)
        val view = inflater.inflate(R.layout.item_plugin_card, parent, false)
        return PluginViewHolder(view)
    }

    override fun onBindViewHolder(holder: PluginViewHolder, position: Int) {
        holder.bind(items[position], formatter, onClick)
    }

    override fun getItemCount(): Int = items.size

    class PluginViewHolder(
        view: View,
    ) : RecyclerView.ViewHolder(view) {
        private val nameText: TextView = view.findViewById(R.id.textPluginName)
        private val versionText: TextView = view.findViewById(R.id.textPluginVersion)
        private val updatedAtText: TextView = view.findViewById(R.id.textPluginUpdatedAt)

        fun bind(
            item: PluginMetadata,
            formatter: SimpleDateFormat,
            onClick: (PluginMetadata) -> Unit,
        ) {
            nameText.text = item.name
            versionText.text = itemView.context.getString(R.string.plugin_version, item.currentVersion)
            updatedAtText.text = itemView.context.getString(
                R.string.plugin_updated_at,
                formatter.format(Date(item.updatedAt))
            )
            itemView.setOnClickListener { onClick(item) }
        }
    }
}
