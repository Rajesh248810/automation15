package com.meesho.hub;

import android.annotation.SuppressLint;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.app.ProgressDialog;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends AppCompatActivity {

    public static final String APP_URL = "http://72.62.231.27:8080/";
    public static final String VERSION_CHECK_URL = "http://72.62.231.27:8080/api/app-version";
    public static final int CURRENT_VERSION_CODE = 2;
    public static final String CURRENT_VERSION_NAME = "1.0.1";

    private WebView webView;
    private ProgressBar progressBar;
    private ValueCallback<Uri[]> fileUploadCallback;
    private final static int FILE_CHOOSER_RESULT_CODE = 1001;
    private final static int INSTALL_PERMISSION_REQUEST_CODE = 1002;
    private String pendingUpdateUrl = null;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        if (getSupportActionBar() != null) {
            getSupportActionBar().hide();
        }

        webView = findViewById(R.id.webView);
        progressBar = findViewById(R.id.progressBar);

        // Smooth scrolling configuration
        webView.setScrollBarStyle(View.SCROLLBARS_INSIDE_OVERLAY);
        webView.setOverScrollMode(View.OVER_SCROLL_IF_CONTENT_SCROLLS);
        webView.setVerticalScrollBarEnabled(false);
        webView.setHorizontalScrollBarEnabled(false);

        // WebView Settings
        WebSettings ws = webView.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDatabaseEnabled(true);
        ws.setCacheMode(WebSettings.LOAD_DEFAULT);
        ws.setAllowFileAccess(true);
        ws.setAllowContentAccess(true);
        ws.setUseWideViewPort(true);
        ws.setLoadWithOverviewMode(true);
        ws.setSupportZoom(false);
        ws.setBuiltInZoomControls(false);

        // User Agent tag for detection
        ws.setUserAgentString(ws.getUserAgentString() + " MeeshoHubApp/" + CURRENT_VERSION_NAME + " (Android)");

        // Cookies
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        // Expose JavaScript Interface to the Web Front-end
        webView.addJavascriptInterface(new WebAppInterface(), "AndroidApp");

        // Navigation & Deep Links
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                // Handle WhatsApp, PhonePe, Paytm, GooglePay UPI, tel, mailto
                if (url.startsWith("whatsapp:") || url.startsWith("upi:") || url.startsWith("tel:") || url.startsWith("mailto:")) {
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                        startActivity(intent);
                        return true;
                    } catch (Exception e) {
                        Toast.makeText(MainActivity.this, "No supported app installed", Toast.LENGTH_SHORT).show();
                        return true;
                    }
                }
                return false;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                progressBar.setVisibility(View.VISIBLE);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
                // Trigger bridge check in web page
                webView.evaluateJavascript("if (window.initNativeAppBridge) { window.initNativeAppBridge(); }", null);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                progressBar.setVisibility(View.GONE);
            }
        });

        // WebChromeClient (Page progress + File chooser upload support)
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                if (newProgress == 100) {
                    progressBar.setVisibility(View.GONE);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (fileUploadCallback != null) {
                    fileUploadCallback.onReceiveValue(null);
                }
                fileUploadCallback = filePathCallback;

                Intent intent = fileChooserParams.createIntent();
                try {
                    startActivityForResult(intent, FILE_CHOOSER_RESULT_CODE);
                } catch (Exception e) {
                    fileUploadCallback = null;
                    return false;
                }
                return true;
            }
        });

        // File Download Listener
        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimeType, long contentLength) {
                try {
                    DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                    request.setMimeType(mimeType);
                    String cookies = CookieManager.getInstance().getCookie(url);
                    request.addRequestHeader("cookie", cookies);
                    request.addRequestHeader("User-Agent", userAgent);
                    request.setDescription("Downloading file...");
                    request.setTitle(URLUtil.guessFileName(url, contentDisposition, mimeType));
                    request.allowScanningByMediaScanner();
                    request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, URLUtil.guessFileName(url, contentDisposition, mimeType));

                    DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    if (dm != null) {
                        dm.enqueue(request);
                        Toast.makeText(MainActivity.this, "Downloading file...", Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception e) {
                    Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                    startActivity(intent);
                }
            }
        });

        // Hardware Back Button Navigation
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack();
                } else {
                    new AlertDialog.Builder(MainActivity.this)
                            .setTitle("Exit Meesho Hub?")
                            .setMessage("Do you want to close the app?")
                            .setPositiveButton("Yes", (dialog, which) -> finish())
                            .setNegativeButton("No", null)
                            .show();
                }
            }
        });

        // Load the Web App
        webView.loadUrl(APP_URL);

        // Silent check for update after 2.5 seconds
        new Handler(Looper.getMainLooper()).postDelayed(() -> checkForUpdate(false), 2500);
    }

    // ----------------- AUTO-UPDATE ENGINE -----------------
    public class WebAppInterface {
        @JavascriptInterface
        public void updateApp() {
            runOnUiThread(() -> checkForUpdate(true));
        }

        @JavascriptInterface
        public int getAppVersionCode() {
            return CURRENT_VERSION_CODE;
        }

        @JavascriptInterface
        public String getAppVersionName() {
            return CURRENT_VERSION_NAME;
        }

        @JavascriptInterface
        public boolean isNativeApp() {
            return true;
        }
    }

    public void checkForUpdate(boolean userTriggered) {
        new Thread(() -> {
            try {
                URL url = new URL(VERSION_CHECK_URL);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                conn.setConnectTimeout(6000);
                conn.setReadTimeout(6000);

                if (conn.getResponseCode() == 200) {
                    BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                    StringBuilder sb = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        sb.append(line);
                    }
                    reader.close();

                    JSONObject json = new JSONObject(sb.toString());
                    int serverCode = json.optInt("version_code", 1);
                    String serverName = json.optString("version_name", "1.0.1");
                    String downloadUrl = json.optString("apk_url", APP_URL + "download");
                    String changelog = json.optString("changelog", "Bug fixes & performance improvements.");

                    runOnUiThread(() -> {
                        if (serverCode > CURRENT_VERSION_CODE) {
                            showUpdateDialog(serverName, downloadUrl, changelog);
                        } else if (userTriggered) {
                            Toast.makeText(MainActivity.this, "Meesho Hub is already up to date! (v" + CURRENT_VERSION_NAME + ")", Toast.LENGTH_LONG).show();
                        }
                    });
                } else if (userTriggered) {
                    runOnUiThread(() -> Toast.makeText(MainActivity.this, "Unable to check updates right now.", Toast.LENGTH_SHORT).show());
                }
            } catch (Exception e) {
                if (userTriggered) {
                    runOnUiThread(() -> Toast.makeText(MainActivity.this, "Error checking updates: " + e.getMessage(), Toast.LENGTH_SHORT).show());
                }
            }
        }).start();
    }

    private void showUpdateDialog(String versionName, String downloadUrl, String changelog) {
        new AlertDialog.Builder(this)
                .setTitle("Update Available (v" + versionName + ")")
                .setMessage("A new update is available!\n\n" + changelog + "\n\nWould you like to install the update now?")
                .setPositiveButton("Update Now", (dialog, which) -> startDownloadAndInstall(downloadUrl))
                .setNegativeButton("Later", null)
                .setCancelable(false)
                .show();
    }

    private void startDownloadAndInstall(String apkUrl) {
        // Android 8.0+ Check for unknown sources install permission
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!getPackageManager().canRequestPackageInstalls()) {
                pendingUpdateUrl = apkUrl;
                new AlertDialog.Builder(this)
                        .setTitle("Permission Needed")
                        .setMessage("To install updates, please enable 'Allow from this source' for Meesho Hub.")
                        .setPositiveButton("Settings", (d, w) -> {
                            Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName()));
                            startActivityForResult(intent, INSTALL_PERMISSION_REQUEST_CODE);
                        })
                        .setNegativeButton("Cancel", null)
                        .show();
                return;
            }
        }

        ProgressDialog progressDialog = new ProgressDialog(this);
        progressDialog.setTitle("Downloading Update");
        progressDialog.setMessage("Please wait while the update is being downloaded...");
        progressDialog.setProgressStyle(ProgressDialog.STYLE_HORIZONTAL);
        progressDialog.setIndeterminate(false);
        progressDialog.setMax(100);
        progressDialog.setCancelable(false);
        progressDialog.show();

        new Thread(() -> {
            try {
                URL url = new URL(apkUrl);
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.connect();

                int fileLength = connection.getContentLength();
                File cacheDir = getExternalCacheDir();
                if (cacheDir == null) cacheDir = getCacheDir();
                File outputFile = new File(cacheDir, "meesho_update.apk");

                InputStream input = new BufferedInputStream(connection.getInputStream());
                OutputStream output = new FileOutputStream(outputFile);

                byte[] data = new byte[4096];
                long total = 0;
                int count;
                while ((count = input.read(data)) != -1) {
                    total += count;
                    if (fileLength > 0) {
                        int progress = (int) (total * 100 / fileLength);
                        runOnUiThread(() -> progressDialog.setProgress(progress));
                    }
                    output.write(data, 0, count);
                }

                output.flush();
                output.close();
                input.close();

                runOnUiThread(() -> {
                    progressDialog.dismiss();
                    installApk(outputFile);
                });

            } catch (Exception e) {
                runOnUiThread(() -> {
                    progressDialog.dismiss();
                    Toast.makeText(MainActivity.this, "Update download failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
                });
            }
        }).start();
    }

    private void installApk(File apkFile) {
        try {
            if (!apkFile.exists()) {
                Toast.makeText(this, "Update file not found", Toast.LENGTH_SHORT).show();
                return;
            }

            Uri apkUri;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                apkUri = FileProvider.getUriForFile(this, getPackageName() + ".provider", apkFile);
            } else {
                apkUri = Uri.fromFile(apkFile);
            }

            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(apkUri, "application/vnd.android.package-archive");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);

        } catch (Exception e) {
            Toast.makeText(this, "Error installing update: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);

        if (requestCode == INSTALL_PERMISSION_REQUEST_CODE) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (getPackageManager().canRequestPackageInstalls() && pendingUpdateUrl != null) {
                    startDownloadAndInstall(pendingUpdateUrl);
                    pendingUpdateUrl = null;
                }
            }
        } else if (requestCode == FILE_CHOOSER_RESULT_CODE) {
            if (fileUploadCallback == null) return;
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getData() != null) {
                    results = new Uri[]{data.getData()};
                } else if (data.getClipData() != null) {
                    int count = data.getClipData().getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) {
                        results[i] = data.getClipData().getItemAt(i).getUri();
                    }
                }
            }
            fileUploadCallback.onReceiveValue(results);
            fileUploadCallback = null;
        }
    }
}
