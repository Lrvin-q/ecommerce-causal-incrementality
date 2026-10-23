import xml.etree.ElementTree as ET
root = ET.parse("out/paper_check/junit.xml").getroot()
for s in root.iter("testsuite"):
    print({k: s.get(k) for k in ["tests","failures","errors","skipped","time"]})
