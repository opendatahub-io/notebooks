## Vulnerability Report by [Trivy](https://trivy.dev)

<details>
  {{- if . }}
    {{- range . }}
      {{- if or (gt (len .Vulnerabilities) 0) (gt (len .Misconfigurations) 0) }}
        <h3>Target: <code>{{- if and (eq .Class "os-pkgs") .Type }}{{ .Type | toString | escapeXML }} ({{ .Class | toString | escapeXML }}){{- else }}{{ .Target | toString | escapeXML }}{{ if .Type }} ({{ .Type | toString | escapeXML }}){{ end }}{{- end }}</code></h3>
        {{- if (gt (len .Vulnerabilities) 0) }}
          <h4>Vulnerabilities ({{ len .Vulnerabilities }})</h4>
          <table>
              <tr>
                  <th>Package</th>
                  <th>ID</th>
                  <th>Severity</th>
                  <th>Installed Version</th>
                  <th>Fixed Version</th>
              </tr>
              {{- range .Vulnerabilities }}
                <tr>
                    <td><code>{{ escapeXML .PkgName }}</code></td>
                    <td>{{ escapeXML .VulnerabilityID }}</td>
                    <td>{{ escapeXML .Severity }}</td>
                    <td>{{ escapeXML .InstalledVersion }}</td>
                    <td>{{ escapeXML .FixedVersion }}</td>
                </tr>
              {{- end }}
          </table>
        {{- end }}
        {{- if (gt (len .Misconfigurations ) 0) }}
          <h4>Misconfigurations</h4>
          <table>
              <tr>
                  <th>Type</th>
                  <th>ID</th>
                  <th>Check</th>
                  <th>Severity</th>
                  <th>Message</th>
              </tr>
              {{- range .Misconfigurations }}
                <tr>
                    <td>{{ escapeXML .Type }}</td>
                    <td>{{ escapeXML .ID }}</td>
                    <td>{{ escapeXML .Title }}</td>
                    <td>{{ escapeXML .Severity }}</td>
                    <td>
                      {{ escapeXML .Message }}
                      <br><a href={{ escapeXML .PrimaryURL | printf "%q" }}>{{ escapeXML .PrimaryURL }}</a></br>
                    </td>
                </tr>
              {{- end }}
          </table>
        {{- end }}
      {{- end }}
    {{- end }}
  {{- else }}
    <h3>Empty report</h3>
  {{- end }}
</details>
