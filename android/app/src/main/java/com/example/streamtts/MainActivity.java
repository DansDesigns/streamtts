package com.example.streamtts;

import android.app.Activity;
import android.os.Bundle;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.view.ViewGroup;
import java.io.File;

/** Tiny smoke-test UI. Copy a compatible model directory into filesDir/models first. */
public final class MainActivity extends Activity {
    private boolean ready = false;
    private EditText input;
    private TextView status;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24, 24, 24, 24);
        status = new TextView(this);
        input = new EditText(this);
        input.setHint("Text to speak");
        input.setMinLines(3);
        Button init = new Button(this);
        init.setText("Load local voice");
        init.setOnClickListener(v -> loadVoice());
        Button speak = new Button(this);
        speak.setText("Speak");
        speak.setOnClickListener(v -> {
            try {
                if (!ready) loadVoice();
                String text = input.getText().toString();
                // This demo supplies one fragment; a real caller can pushText
                // repeatedly for every fragment received from its text stream.
                NativeTts.pushText(text + " ");
                NativeTts.flush();
                status.setText("Text queued for speech.");
            } catch (Exception ex) { status.setText("TTS error: " + ex.getMessage()); }
        });
        root.addView(status, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(input, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(init);
        root.addView(speak);
        setContentView(root);
        status.setText("Copy the model files into " + new File(getFilesDir(), "models").getAbsolutePath());
    }

    private void loadVoice() {
        File dir = new File(getFilesDir(), "models");
        File model = new File(dir, "en_US-amy-low.onnx");
        File tokens = new File(dir, "tokens.txt");
        File data = new File(dir, "espeak-ng-data");
        if (!model.isFile() || !tokens.isFile()) {
            throw new IllegalStateException("Expected en_US-amy-low.onnx and tokens.txt in " + dir);
        }
        NativeTts.init(model.getAbsolutePath(), tokens.getAbsolutePath(), data.isDirectory() ? data.getAbsolutePath() : "");
        ready = true;
        status.setText("Voice loaded. Sample model runs locally on this device.");
    }

    @Override protected void onDestroy() {
        if (ready) NativeTts.shutdown();
        super.onDestroy();
    }
}
