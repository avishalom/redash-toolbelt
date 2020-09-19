import click

from redash_toolbelt import Redash


## https://dashboards.sednanetwork.com copy-of-users-and-teams_191 SLUG PFX  customer_aal --api-key 2JD
def duplicate(client, slug, prefix=None, new_slug=None, to_source=None):
    # Copped this logic directly from Redash.duplicate_dashboard
    current_dashboard = client.dashboard(slug)
    new_dash_name = f'{to_source["name"]} {new_slug}' or "Copy of: {}".format(current_dashboard["name"])
    new_dashboard = client.create_dashboard(new_dash_name)
    json_params = {"is_draft": False}
    if current_dashboard["tags"]:
        json_params['tags'] = current_dashboard["tags"]
    client.update_dashboard(new_dashboard["id"], json_params)

    # Widgets can hold text boxes or visualizations. Filter out text boxes.
    # I use a dictionary here because it de-duplicates query IDs
    queries_to_duplicate = {
        widget["visualization"]["query"]["id"]: widget["visualization"]["query"]
        for widget in current_dashboard.get("widgets", [])
        if "visualization" in widget
    }

    # Fetch full query details for the old query IDs
    # Duplicate the query and store the result
    old_vs_new_query_pairs = [
        {
            "old_query": client.query(old_query.get('id')),
            "new_query": client.duplicate_query(
                old_query.get("id"), new_name=" ".join([prefix + old_query.get("name")])
            ),
        }
        for old_query in queries_to_duplicate.values()
    ]

    # Compare old visualizations to new ones
    # Create a mapping of old visualization IDs to new ones
    old_viz_vs_new_viz = {
        old_viz.get("id"): new_viz.get("id")
        for pair in old_vs_new_query_pairs
        for old_viz in pair["old_query"].get("visualizations")
        for new_viz in pair["new_query"].get("visualizations")
        if old_viz.get("options") == new_viz.get("options")
    }

    # This is a version of the same logic from Redash.duplicate_dashboard
    # But it substitutes in the new visualiation ID pointing at the copied query.
    for widget in current_dashboard["widgets"]:
        visualization_id = None
        if "visualization" in widget:
            visualization_id = old_viz_vs_new_viz.get(widget["visualization"]["id"])
        client.create_widget(
            new_dashboard["id"], visualization_id, widget["text"], widget["options"]
        )

    # Now update the new queries
    sources = client.data_sources()
    q1 = old_vs_new_query_pairs[0]['old_query']
    from_sources = [s for s in sources if s['id'] == q1['data_source_id']]
    if len(from_sources) != 1:
        print('bad source', q1, from_sources)
        return
    from_source = from_sources[0]

    for pair in old_vs_new_query_pairs:
        new_query = pair["new_query"]
        name, qid, query, options = [new_query[x] for x in 'name id query options'.split()]
        # Update the forked query
        name = name.split(prefix)[-1]

        qname = f'{to_source["name"]} {new_slug} {name}'
        query = query.replace(from_source["name"], to_source["name"])

        json_params = {'query': query,
                       'name': qname,
                       'data_source_id': to_source['id'],
                       'is_draft': False
                       }

        # update
        client.update_query(qid, data=json_params)

    return new_dashboard


@click.command()
@click.argument("redash_host")
@click.argument("slug")
@click.argument("prefix")
@click.argument("new_slug")
@click.argument("to_client")
@click.option(
    "--api-key",
    "api_key",
    envvar="REDASH_API_KEY",
    show_envvar=True,
    prompt="API Key",
    help="User API Key",
)
# note I am making an assumption that the data source name is the same as the schema name being replaced.
def main(redash_host, slug, prefix, new_slug, to_client, api_key):
    """Search for EMAIL in queries and query results, output query URL if found."""

    client = Redash(redash_host, api_key)
    sources = client.data_sources()

    if to_client.lower() == 'all':
        for source in sources:
            if source['name'].startswith('customer_'):
                print(source)
                duplicate(client, slug, prefix, new_slug, source)

    else:
        to_sources = [s for s in sources if s['name'] == to_client]
        if len(to_sources) != 1:
            print('bad source', to_client, to_sources)
            return
        duplicate(client, slug, prefix, new_slug, to_sources[0])


if __name__ == "__main__":
    main()
