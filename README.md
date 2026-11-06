🌐 wispbyte-cloudflare
A lightweight, containerized VLESS over WebSocket (WS) + TLS deployment designed for Wispbyte using Cloudflare Zero Trust Tunnels (⁠cloudflared⁠).
By routing traffic through an outbound Cloudflare Tunnel, this setup eliminates the need for open inbound ports or dedicated public IPv4 addresses on the host container while providing native Cloudflare CDN TLS termination and SNI/Host fronting support.
✨ Features
￼ Zero Inbound Port Requirements: Connects outbound to Cloudflare's edge via ⁠cloudflared⁠.
￼ Automated Provisioning: Dynamically configures Xray/VLESS and connects the tunnel on container startup using environment variables.
￼ CDN & Bug-Host Compatible: Works seamlessly with Cloudflare Anycast IPs and custom SNI/Addr bug hosts.
￼ Lightweight Footprint: Optimized for low-resource container environments on Wispbyte.
🛠️ Prerequisites
1. A Wispbyte account with an active container server.
2. A Cloudflare account with an active domain added to your zone.
3. Access to the Cloudflare Zero Trust Dashboard.
🚀 Deployment Guide
Step 1: Create a Cloudflare Zero Trust Tunnel
1. Log in to the Cloudflare Zero Trust Dashboard.
2. Navigate to Networks > Tunnels and click Create a tunnel.
3. Select Cloudflared as the connector type, name your tunnel (e.g., ⁠wispbyte-vless⁠), and click Save tunnel.
4. Copy the Tunnel Token from the installation command (the long string starting with ⁠eyJ...⁠).
5. Under the Public Hostname tab, click Add a public hostname:
￼ Subdomain: ⁠vless⁠ (or any subdomain of your choice)
￼ Domain: Select your Cloudflare domain (e.g., ⁠example.com⁠)
￼ Service Type: ⁠HTTP⁠
￼ URL: ⁠localhost:8080⁠ (Note: Ensure this port matches the internal WebSocket listener port in your ⁠config.json⁠ / startup script)
6. Click Save hostname.
Step 2: Upload Files to Wispbyte
Step 3: Configure Environment Variables
In your Wispbyte panel, go to the Startup / Variables tab and configure the following environment variables:
Variable
Description
Example
VLESS_UUID
Your unique UUIDv4 identifier for client authentication
a1b2c3d4-e5f6-7890-abcd-ef1234567890
CLOUDFLARE_TUNNEL_TOKEN
The token copied from your Cloudflare Zero Trust Tunnel
eyJhIjoi...

Step 4: Start the Server
1. Navigate to the Console tab in Wispbyte and click Start.
2. Wait for the startup script to initialize the Xray core and establish the Cloudflare Tunnel connection.
3. Once initialized, copy the generated ⁠vless://⁠ link output in the console (or construct it manually using the template below).
📱 Client Configuration
Import the generated ⁠vless://⁠ URI into your client (Shadowrocket, v2rayNG, Nekoray, Streisand, or Hiddify), or configure it manually with these parameters:
￼ Type / Protocol: ⁠VLESS⁠
￼ Address: ⁠your-subdomain.example.com⁠ (or any Cloudflare CDN IP / Bug Host)
￼ Port: ⁠443⁠
￼ UUID: Your ⁠VLESS_UUID⁠ value
￼ Transport: ⁠ws⁠ (WebSocket)
￼ Host: ⁠your-subdomain.example.com⁠
￼ Path: ⁠/⁠ (or the custom WebSocket path defined in your Xray configuration)
￼ TLS: ⁠Enabled⁠ (⁠On⁠)
￼ SNI: ⁠your-subdomain.example.com⁠ (or your bug host if required by your ISP)
￼ ALPN: ⁠http/1.1⁠
URI Template
⚠️ Disclaimer
This project is intended solely for educational purposes, network testing, and personal privacy research. Please ensure compliance with the Terms of Service of both Wispbyte and Cloudflare when deploying this software.

Supported:
• Northflank
• Wispbyte
• MS Hosting
• Botkeep
• Railway