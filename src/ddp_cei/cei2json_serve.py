from flask import Flask, render_template
from .cei2json import load_cei2json
from .fsdb_standoff import StandoffStrIdx


def create_app(root: str = "/home/anguelos/data/monasterium/", filename: str = "CH.cei2json.json", fsdb_glob: str = "*/*/*", verbose: bool= False) -> Flask:
    tenor_word2md5, abstract_word2md5, word2md5, abstract_idx, tenor_idx = load_cei2json(root=root, filename=filename, fsdb_glob=fsdb_glob, verbose=verbose)
    app = Flask(
        __name__,
        template_folder="templates",  # package-relative
        static_folder="static",      # package-relative
    )
    app.default_format = ["json", "html"][0]
    
    app.standoff_tenor_idx = StandoffStrIdx.from_md5dict(tenor_idx)
    app.standoff_abstract_idx = StandoffStrIdx.from_md5dict(abstract_idx)

    @app.route("/")
    def index():
        idx_tbl = [("Tenors", len(app.standoff_tenor_idx), len(app.standoff_tenor_idx.rev_idx)), ("Abstracts", len(app.standoff_abstract_idx), len(app.standoff_abstract_idx.rev_idx))]
        return render_template("index.html", indexes = idx_tbl)
    return app

    @app.route("/search_abstracts/<pattern>", methods=['GET'])
    def search_abstracts(pattern):
        file_format = request.args.get('format')
        if file_format is None:
            file_format = app.default_format
        if file_format == "json":
            return jsonify(data)  # Return JSON response
        if file_format == "html":
            return render_template('ranked_charter_list_responce.html', data=data, fsdb_url=app.fsdb_url)  # Return HTML response
        return "Unsupported format", 406    


def serve_cli_main():
    import fargv
    p = {
        "root": ("/home/anguelos/data/monasterium/", "Root folder containing the cei2json files"),
        "filename": ("CH.cei2json.json", "Filename pattern to search for in the cei2json files"),
        "fsdb_glob": ("*/*/*", "Filesystem glob pattern to locate the cei2json files"),
        "verbose": (False, "Verbose output during loading"),
        "host": ("0.0.0.0", "Host to serve the Flask app on"),
        "port": (5000, "Port to serve the Flask app on"),
    }
    args, _ = fargv.fargv(p)
    app = create_app(root=args.root, filename=args.filename, verbose=args.verbose, fsdb_glob=args.fsdb_glob)
    print("Starting server on http{}://{}:{}".format("s" if args.port == 443 else "", args.host, args.port))
    app.run(host=args.host, port=args.port)
