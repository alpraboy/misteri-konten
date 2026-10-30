import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import captions
import footage

class V63Tests(unittest.TestCase):
    def test_subtitle_groups_have_limited_width(self):
        words = [{'text': t, 'start': i * .3, 'end': i*.3+.25} for i,t in enumerate(['Ini','adalah','sebuah','misteri','yang','belum','terpecahkan','sampai','sekarang'])]
        script = {'total_duration': 4, 'title': 'Tes Misteri', 'scenes': [{'duration': 4, 'start': 0, 'words': words, 'onscreen': ''}]}
        cfg = {'style': {'font':'DejaVu Sans','size':40,'title_size':48,'color':'&H0000B0FF&','uppercase':False}}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cap.ass'; captions.build_ass(script,cfg,p)
            text=p.read_text()
        self.assertNotIn('PERTANYAAN', text)
        # no subtitle event may contain the whole long sequence as a single line
        self.assertNotIn('Ini adalah sebuah misteri yang belum terpecahkan sampai sekarang', text)
        self.assertIn('pos(540,1490)', text)

    def test_pixabay_irrelevant_metadata_rejected(self):
        self.assertLess(footage._relevance('ancient temple ruins', {'meta':'ocean fish'}), .2)

    def test_provider_ranked_results_allowed_when_metadata_missing(self):
        self.assertEqual(footage._relevance('abandoned house night', {'meta':'', 'provider_ranked':True}), 1.0)

if __name__ == '__main__': unittest.main()
